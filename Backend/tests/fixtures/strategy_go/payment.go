package payment

type PaymentStrategy interface {
	Pay(amount float64)
}

type CreditCardStrategy struct{}

func (c *CreditCardStrategy) Pay(amount float64) {
	c.Charge(amount)
}

func (c *CreditCardStrategy) Charge(amount float64) {}

type PayPalStrategy struct{}

func (p *PayPalStrategy) Pay(amount float64) {
	p.Send(amount)
}

func (p *PayPalStrategy) Send(amount float64) {}

type Checkout struct {
	Strategy PaymentStrategy
}

func (c *Checkout) Process(amount float64) {
	c.Strategy.Pay(amount)
}
