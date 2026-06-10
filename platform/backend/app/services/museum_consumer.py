# def handle_museum_created(event):
#
#     museum_repository.create(
#         event.payload
#     )
#
#     print("Museum opgeslagen")

def handle_museum_created(event):
    print(event.payload)