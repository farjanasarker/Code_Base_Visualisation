class BankAccount:
    def __init__(self, name, balance):
        self.name = name
        self.balance = balance
    def deposit(self, amount):
        self.amount = amount
        self.balance += amount
        return self.balance
    def withdraw(self, amount):
        self.amount = amount
        self.balance -= amount
        return self.balance
    def get_balance(self):
        return self.balance
    def get_name(self):
        return self.name
        
b1 = BankAccount("Naima", 100000)
print(b1.get_name())
print(b1.get_balance())
b1.deposit(5000)
print(b1.get_balance())
b1.withdraw(10000)
print(b1.get_balance())