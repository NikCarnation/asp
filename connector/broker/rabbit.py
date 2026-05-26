import json

import aio_pika
from agent.models.schemas import NormalizedAlert


class RabbitPublisher:
    def __init__(self, host: str = "localhost", port: int = 5672,
                 user: str = "guest", password: str = "guest",
                 queue: str = "aisoc_alerts"):
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
        body = alert.model_dump_json().encode()
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=self.queue_name,
        )

    async def close(self):
        if self.connection:
            await self.connection.close()


class RabbitConsumer:
    def __init__(self, host: str = "localhost", port: int = 5672,
                 user: str = "guest", password: str = "guest",
                 queue: str = "aisoc_alerts"):
        self.url = f"amqp://{user}:{password}@{host}:{port}/"
        self.queue_name = queue
        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.RobustChannel | None = None
        self.queue: aio_pika.Queue | None = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel()
        # Process one message at a time to guarantee ordering
        await self.channel.set_qos(prefetch_count=1)
        self.queue = await self.channel.declare_queue(self.queue_name, durable=True)

    async def consume(self, callback) -> None:
        self.connection = None
        self.channel = None
        self.queue = None
        await self.connect()
        async with self.queue.iterator() as queue_iter:
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
