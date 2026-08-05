interface PaymentStrategy {
  pay(amount: number): void;
}

class CreditCardStrategy implements PaymentStrategy {
  pay(amount: number): void {
    this.charge(amount);
  }
  charge(amount: number): void {}
}

class PayPalStrategy implements PaymentStrategy {
  pay(amount: number): void {
    this.send(amount);
  }
  send(amount: number): void {}
}

class Checkout {
  strategy: PaymentStrategy;
  constructor(strategy: PaymentStrategy) {
    this.strategy = strategy;
  }
  process(amount: number): void {
    this.strategy.pay(amount);
  }
}
