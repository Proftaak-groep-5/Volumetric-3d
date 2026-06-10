from typing import Callable, Dict, List
from .event_models import BaseEvent

class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable):
            if event_type not in self.subscribers:
                self.subscribers[event_type] = []
            self.subscribers[event_type].append(handler)


    def publish(self, event: BaseEvent):
        handlers = self.subscribers.get(event.event_type, [])
        for handler in handlers:
            handler(event)