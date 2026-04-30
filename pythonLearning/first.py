print("hello world")
print('helllo', 'world')
x=5
y="naima"
print(x)
print(y)
x,y,z = "naima","saila","farjana"
print(x)
print(y)
print(z)
fruits = ["apple", "banana", "cherry"]
x,y,z = fruits
print(x)
print(y)
print(z)
x = "awesome"
def myfunc():
    x="fantastic"
    print("Python is " + x)
myfunc()
print("Python is " + x)
def myfunc():
    global x
    x = "fantastic"
    print("Python is " + x)
myfunc()
print("Python is " + x)
  
import random
print(random.randrange(1,7))
print("It's alright")
print("He is called 'Naima'")
print('He is called "Naima"')
b = "Hello, World!"
print(b[2:5])
print(b[:5])
print(b[2:])
print(b[-5:-2]) 
print(b.upper())
print(b.strip())
print(b.replace("H", "J"))
print(b.split(','))
#string concatination 
a="Naima"
b="Sarker"           
c=a+b
print(c)
age = 23
txt = f"My name is naima, and I am {age}"
print(txt)
price = 49
txt = f"The price is {price:.2f} dollars"
print(txt)
#list
mylist = ["apple", "banana", "cherry"]
print(mylist)
print(len(mylist))
list1 = ["abc", 34, True]
print(type(list1))
thislist = list(("apple", "banana", "cherry"))
print(thislist)
if "apple" in thislist:
    print("Yes, 'apple' is in the fruits list")
tropical = ["mango", "pineapple", "papaya"]
thislist.extend(tropical)
print(thislist)
thistuple = ("orange", "kiwi")
thislist.extend(thistuple)
print(thislist)
for x in thislist:
    print(x)
for i in range(len(thislist)):
    print(thislist[i])
def myfunc(n):
    return abs(n-50)
mylist = [100, 50, 65, 82, 23]
mylist.sort(key=myfunc)
print(mylist)
#tuple
thistuple = ("naima","Sarker","Farjana")
print(thistuple)
tuple1 = ("apple",)
print(tuple1)
print(type(thistuple))
y = ("Shaila",)
thistuple += y
print(thistuple)