pub trait PaymentStrategy {
    fn pay(&self, amount: f64);
}

pub struct CreditCardStrategy {}

impl PaymentStrategy for CreditCardStrategy {
    fn pay(&self, amount: f64) {
        self.charge(amount);
    }
}

impl CreditCardStrategy {
    fn charge(&self, amount: f64) {}
}

pub struct PayPalStrategy {}

impl PaymentStrategy for PayPalStrategy {
    fn pay(&self, amount: f64) {
        self.send(amount);
    }
}

impl PayPalStrategy {
    fn send(&self, amount: f64) {}
}

pub struct Checkout {
    pub strategy: Box<dyn PaymentStrategy>,
}

impl Checkout {
    pub fn process(&self, amount: f64) {
        self.strategy.pay(amount);
    }
}
