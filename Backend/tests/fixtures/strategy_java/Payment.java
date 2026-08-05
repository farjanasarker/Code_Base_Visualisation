interface PaymentStrategy {
    void pay(double amount);
}

class CreditCardStrategy implements PaymentStrategy {
    public void pay(double amount) {
        charge(amount);
    }
    public void charge(double amount) {}
}

class PayPalStrategy implements PaymentStrategy {
    public void pay(double amount) {
        send(amount);
    }
    public void send(double amount) {}
}

class Checkout {
    private PaymentStrategy strategy;

    public Checkout(PaymentStrategy strategy) {
        this.strategy = strategy;
    }

    public void process(double amount) {
        strategy.pay(amount);
    }
}
