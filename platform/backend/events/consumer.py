import pika, json

def callback(ch, method, properties, body):
    event = json.loads(body)

    print ("Received:", event)

async def handle_museum_created(message: aio_pika.IncomingMessage):
    async with message.process():
        event = json.loads(message.body)

        print("Museum created event received:", event)