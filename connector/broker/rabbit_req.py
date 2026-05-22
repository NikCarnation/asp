from typing import Optional
import aio_pika
from aio_pika.abc import AbstractIncomingMessage
import asyncio


async def main(
    host: str = "localhost",
    port: int = 5672,
    user: str = "guest",
    password: str = "guest",
    queue_name: str = "aisoc_alerts"):
    url = f"amqp://{user}:{password}@{host}:{port}/"

    connection = await aio_pika.connect_robust(url)
    channel = await connection.channel()
    queue = await channel.declare_queue(queue_name, auto_delete=False, durable=True)

    incoming_message: Optional[AbstractIncomingMessage] = await queue.get(
        timeout=5, fail=False
    )

    if incoming_message:
        async with incoming_message.process():
            print(f"Received: {incoming_message.body.decode()}")
    else:
        print("Queue empty")

    await connection.close()


if __name__ == "__main__":
    asyncio.run(main("localhost", 5672, "guest", "guest", "aisoc_alerts"))