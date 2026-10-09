"""Loopback byte tunnel for one test Worker; never log or inspect PostgreSQL traffic."""

import argparse
import asyncio
from pathlib import Path


async def run(args):
    writers = set()

    async def accept(reader, writer):
        if Path(args.drop).exists():
            writer.close()
            return
        remote_reader, remote_writer = await asyncio.open_connection("127.0.0.1", args.target)
        writers.update((writer, remote_writer))

        async def forward(source, destination):
            try:
                while data := await source.read(65536):
                    destination.write(data)
                    await destination.drain()
            finally:
                destination.close()

        try:
            await asyncio.gather(forward(reader, remote_writer), forward(remote_reader, writer))
        except (ConnectionError, OSError):
            pass
        finally:
            writers.difference_update((writer, remote_writer))
            writer.close()
            remote_writer.close()

    server = await asyncio.start_server(accept, "127.0.0.1", args.port)
    Path(args.ready).write_text("ready")
    async with server:
        while True:
            if Path(args.drop).exists():
                for writer in tuple(writers):
                    writer.close()
            await asyncio.sleep(0.05)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--drop", required=True)
    parser.add_argument("--ready", required=True)
    asyncio.run(run(parser.parse_args()))
