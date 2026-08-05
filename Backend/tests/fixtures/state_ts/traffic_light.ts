interface State {
  handle(): void;
}

class TrafficLight {
  state: State;
  setState(state: State): void {
    this.state = state;
  }
  request(): void {
    this.state.handle();
  }
}

class RedState implements State {
  context: TrafficLight;
  constructor(context: TrafficLight) {
    this.context = context;
  }
  handle(): void {
    this.context.setState(new GreenState(this.context));
  }
}

class GreenState implements State {
  context: TrafficLight;
  constructor(context: TrafficLight) {
    this.context = context;
  }
  handle(): void {
    this.context.setState(new RedState(this.context));
  }
}
