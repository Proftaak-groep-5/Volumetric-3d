import pika, json

def publish_event(event:dict):
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host='localhost')
    )
    channel = connection.channel()

    channel.queue_declare(queue='orders')

    channel.basic_publish(
        exchange='',
        routing_key='orders',
        body=json.dumpbs(event)
    )

    connection.close()