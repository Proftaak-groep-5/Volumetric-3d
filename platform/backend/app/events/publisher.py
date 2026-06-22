import pika, json


# def publish_museum_event(event_data: dict):
#     try:
#         connection = pika.BlockingConnection(
#             pika.ConnectionParameters(host='localhost')
#         )
#         channel = connection.channel()
#
#         channel.queue_declare(queue='museum_events', durable=True, arguments={'x-queue-type': 'quorum'})
#
#         event = {
#             'event_type': 'museum_created',
#             'name': event_data.get('name'),
#             'description': event_data.get('description')
#         }
#         channel.basic_publish(
#             exchange='',
#             routing_key='museum_events',
#             body=json.dumps(event).encode('utf-8'),
#             properties=pika.BasicProperties(delivery_mode=2)
#         )
#         print(f"[x] Published event: {event}")
#         connection.close()
#     except Exception as e:
#         print(f"Error publishing event: {e}")

def publish_museum_event(event_data: dict):
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            print(f"[DEBUG] Attempt {attempt + 1}/{max_retries}: Connecting to RabbitMQ at localhost:5672")

            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host='localhost',
                    port=5672,
                    connection_attempts=3,
                    retry_delay=2
                )
            )
            channel = connection.channel()

            channel.queue_declare(queue='museum_events', durable=True, arguments={'x-queue-type': 'quorum'})

            event = {
                'event_type': 'museum_created',
                'name': event_data.get('name'),
                'description': event_data.get('description'),
                'image_Url': event_data.get('image_Url')
            }

            print(f"[DEBUG] Publishing event: {event}")

            channel.basic_publish(
                exchange='',
                routing_key='museum_events',
                body=json.dumps(event).encode('utf-8'),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"[x] Successfully published event: {event}")
            connection.close()
            return  # Success, exit

        except pika.exceptions.AMQPConnectionError as e:
            print(f"[ERROR] Connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"[INFO] Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
        except Exception as e:
            print(f"[ERROR] Error publishing event: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

    print("[CRITICAL] Failed to publish event after all retries")
