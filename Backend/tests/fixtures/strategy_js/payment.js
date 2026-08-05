// EXPECTED NON-MATCH — see tests/test_strategy_fixtures.py.
//
// This is the same Strategy shape as the other strategy_<lang> fixtures,
// but plain JavaScript has no type annotations anywhere in the language:
// `this.strategy = strategy` carries no information that `strategy` is a
// `PaymentStrategy`, so composition_field_of_type has no field-type signal
// to resolve a HAS_FIELD edge from at all. This isn't a parser bug to fix —
// the information genuinely doesn't exist in the source. Composition-based
// GoF patterns (Strategy, Decorator, Composite, ...) are structurally
// undetectable in untyped JS without a type source (JSDoc comments would be
// one, out of scope for Phase 0).
class PaymentStrategy {
  pay(amount) {
    throw new Error("not implemented");
  }
}

class CreditCardStrategy extends PaymentStrategy {
  pay(amount) {
    this.charge(amount);
  }
  charge(amount) {}
}

class PayPalStrategy extends PaymentStrategy {
  pay(amount) {
    this.send(amount);
  }
  send(amount) {}
}

class Checkout {
  constructor(strategy) {
    this.strategy = strategy;
  }
  process(amount) {
    this.strategy.pay(amount);
  }
}

module.exports = { PaymentStrategy, CreditCardStrategy, PayPalStrategy, Checkout };
