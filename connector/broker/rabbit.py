import json

import aio_pika

from agent.models.schemas import NormalizedAlert


class RabbitPublisher:
    def __init__(self, host: str, port: int, user: str, password: str, queue: str):
        self.url = f"amqp://{user}:{password}@{host}:{port}/"
        self.queue_name = queue
        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.RobustChannel | None = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel()
        await self.channel.declare_queue(self.queue_name, durable=True)

    async def publish(self, alert: NormalizedAlert):
        if not self.channel:
            await self.connect()
        body = alert.model_dump_json(default=str).encode()
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=self.queue_name,
        )

    async def close(self):
        if self.connection:
            await self.connection.close()


class RabbitConsumer:
    def __init__(self, host: str, port: int, user: str, password: str, queue: str):
        self.url = f"amqp://{user}:{password}@{host}:{port}/"
        self.queue_name = queue
        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.RobustChannel | None = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel()
        await self.channel.declare_queue(self.queue_name, durable=True)

    async def consume(self, callback) -> None:
        if not self.channel:
            await self.connect()
        async with self.channel.iterator(self.queue_name) as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body.decode())
                        alert = NormalizedAlert(**data)
                        await callback(alert)
                    except Exception as e:
                        print(f"Error processing message: {e}")

    async def close(self):
        if self.connection:
            await self.connection.close()
