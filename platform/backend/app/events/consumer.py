import pika, json
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from ..contracts.museum_contract import CreateMuseumContract, ReceivedCreateMuseumContract


# ANY EVENT
# def callback(ch, method, properties, body):
#     event = json.loads(body)
#     print ("Received:", event)
#
#     ch.basic_consume(queue='orders',
#                      auto_ack=True,
#                      on_message_callback=callback)
#     ch.start_consuming()

# MUSEUM EVENTS
async def consume_museum_events(db: AsyncSession):
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host='localhost', port=5672, connection_attempts=3, retry_delay=2)
    )
    channel = connection.channel()
    channel.queue_declare(queue='museum_events', durable=True, arguments={'x-queue-type': 'quorum'})

    def callback(ch, method, prop, body):
        try:
            newbody = body.decode("utf-8")

            raw = json.loads(newbody)
            event = ReceivedCreateMuseumContract(**raw)
            print(f"Received museum event: {event}")

            if event.event_type == 'museum_created':
                loop = asyncio.get_event_loop()
                loop.create_task(handle_museum_created(event, db))
                ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print(f"Error processing event: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_consume(queue='museum_events', on_message_callback=callback, auto_ack=False)
    print("Waiting for museum events...")
    channel.start_consuming()

async def handle_museum_created(event: ReceivedCreateMuseumContract, db: AsyncSession):
    """Handle museum creation event and save to database"""
    from ..app.services import museum as museum_service

    try:
        museum = await museum_service.create_museum(
            db=db,
            name=event.name,
            description=event.description
        )
        print(f"Museum created in DB: {museum.museumid}")
        return museum
    except Exception as e:
        print(f"Error creating museum: {e}")