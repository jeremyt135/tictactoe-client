from functools import partial
import asyncio


def on_read(read_chunks: asyncio.Queue, fut: asyncio.Future):
    if fut.cancelled():
        return
    elif fut.exception():
        read_chunks.put_nowait('EOF')
    else:
        line = fut.result()
        if not line or not line.endswith(b'\n'):
            # EOF received - line is empty or incomplete
            read_chunks.put_nowait('EOF')
        line = line.decode('utf-8').rstrip('\n')
        read_chunks.put_nowait(line)


async def game_client(socket_address: (str, int), gui_queue: asyncio.Queue, client_queue: asyncio.Queue) -> None:
    """
    Runs a network client for interacting with the game server.
    """
    reader: asyncio.StreamReader = None
    writer: asyncio.StreamWriter = None
    try:
        reader, writer = await asyncio.open_connection(*socket_address)
    except ConnectionRefusedError:
        client_queue.put_nowait(
            {'status': 'error', 'data': 'connection refused'})
        return

    connected = True
    read_chunks = asyncio.Queue()
    pending_writes = asyncio.Queue(maxsize=1)
    read_done, read_task = True, None
    write_done, write_task = True, None

    # interact with the server forever until it closes its end of the connection
    while connected:
        if read_done:
            # schedule a new read
            read_task = asyncio.create_task(reader.readline())
            read_task.add_done_callback(
                partial(on_read, read_chunks)
            )
            read_done = False
        elif read_task:
            read_done = read_task.done()
        await asyncio.sleep(0.001)

        # let the network client check for unrecoverable errors
        while not read_chunks.empty():
            chunk = read_chunks.get_nowait()
            #print(f"client: received '{chunk}''")

            if chunk in ('EOF'):
                client_queue.put_nowait(
                    {'status': 'error', 'data': 'connection closed'})
                connected = False
                break
            elif chunk == 'TICTACTOE':
                # schedule a write
                pending_writes.put_nowait('TICTACTOE\n')
            else:
                # send anything else to gui
                client_queue.put_nowait(
                    {'status': 'ok', 'data': chunk})
        await asyncio.sleep(0.001)

        # check if the gui was closed
        if not gui_queue.empty():
            gui_message = gui_queue.get_nowait()
            # check if a closed event happened
            if gui_message == 'closed':
                break
            # not a close, so send whatever the action is
            pending_writes.put_nowait(gui_message)

        if write_done and not pending_writes.empty():
            # schedule a new write
            data = bytes(pending_writes.get_nowait(), 'utf-8')
            writer.write(data)
            write_task = asyncio.create_task(writer.drain())
            write_done = False
        elif write_task:
            write_done = write_task.done()

    # cancel pending tasks
    pending_tasks = []
    if read_task:
        read_task.cancel()
        pending_tasks.append(read_task)
    if write_task:
        write_task.cancel()
        pending_tasks.append(write_task)
    # wait until cancelled
    await asyncio.wait(pending_tasks)

    writer.close()
    await writer.wait_closed()
