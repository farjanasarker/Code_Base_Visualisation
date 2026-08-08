abstract class Game {
  abstract initialize(): void;

  play(): void {
    this.initialize();
  }
}

class Football extends Game {
  initialize(): void {}
}
