const listeners = [];

function subscribeToEvent(handler) {
  listeners.push(handler);
}

function publishEvent(event) {
  listeners.forEach((handler) => handler(event));
}

module.exports = { subscribeToEvent, publishEvent };
