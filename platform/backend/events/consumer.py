import pika, json

def callback(ch, method, properties, body):
    event = json.loads(body)

    print ("Received:", event)
