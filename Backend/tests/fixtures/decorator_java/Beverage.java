interface Beverage {
    double cost();
}

class Espresso implements Beverage {
    public double cost() { return 1.99; }
}

abstract class BeverageDecorator implements Beverage {
    protected Beverage beverage;

    BeverageDecorator(Beverage beverage) {
        this.beverage = beverage;
    }
}

class MilkDecorator extends BeverageDecorator {
    MilkDecorator(Beverage beverage) {
        super(beverage);
    }

    public double cost() {
        logAddition();
        return beverage.cost() + 0.5;
    }

    private void logAddition() {
        System.out.println("Adding milk");
    }
}

class SugarDecorator extends BeverageDecorator {
    SugarDecorator(Beverage beverage) {
        super(beverage);
    }

    public double cost() {
        logAddition();
        return beverage.cost() + 0.2;
    }

    private void logAddition() {
        System.out.println("Adding sugar");
    }
}
