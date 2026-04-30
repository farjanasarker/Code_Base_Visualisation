# print("Enter a number:")
# x = int(input())
# if (x%2 == 0):
#     print("Even")
# else:
#     print("odd")
a = 33
b = 2
c = 32
if a>b and c>a:
    print("c is greater")
elif a>b and a>c:
    print("a is greater")
else:
    print("b is greater")

def my_function():
    mylist = [10, 15, 20, 30, 40]
    sum = 0
    for x in mylist:
        sum += x
    print("The sum of the all numbers are:",sum)
my_function()   

print("Enter a string:")
str = input()
print("reverse of the string is:",str[::-1])
vowle = 0
for x in str:
    if x=="a" or x=="e" or x=="i" or x=="o" or x=="u":
        vowle += 1
print("The number of vowle in the string is:",vowle)

def isPailndrome(str):
    if str == str[::-1]:
        print("The string is palindrome")
    else:
        print("The string is not palindrome")
str = input("Enter a string:")
isPailndrome(str)

def fibonaci(n):
    a = 0
    b = 1
    if n == 1:
       print(a)
    else:
       print(a)
       print(b)
       for i in range(2,n):
           c = a+b
           a = b
           b = c
           print(c)

fib = int(input("Enter a number:"))
fibonaci(fib)

def factorial(n):
    if n == 0:
        return 1
    else:
        return n*factorial(n-1)
fact = int(input("Enter a number:"))
print("The factorial of the number is:",factorial(fact))

def anagram(str1, str2):
    if len(str1) != len(str2):
        print("The string is not anagram")
    else:
        if sorted(str1) == sorted(str2):
            print("The string is anagram")
        else:
            print("The string is not anagram")
str1 = "cdab"
str2 = "abcd"
anagram(str1, str2)

def primeNumber(n):
    if n>1:
        for i in range(2,n):
            if n%i == 0:
                print("The number is not prime")
                break
        else:
            print("The number is prime")
    else:
        print("The number is not prime")
primeNumber(10)

def reverseString(str):
    if len(str) == 0:
        return str
    else:
        i = len(str)-1
        str2 = ""
        for j in range(i,-1,-1):
            str2 += str[j]
        return str2
str = "hello"
print("The reverse of the string is:",reverseString(str))