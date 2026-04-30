def secondlargest(mylist):
    mylist.sort()
    print("The second Largest number is:", mylist[-2])

mylist = [2, 10, 9, 4, 8, 27,20]
secondlargest(mylist)

def removeduplicates(mylist1 , index = 0):

    if index >= len(mylist1)-1:
        print("The list after removing duplicates is:", mylist1)   
        return
    
    if mylist1[index] == mylist1[index+1]:
        mylist1.pop(index)
        removeduplicates(mylist1, index)    
    else:
        removeduplicates(mylist1, index+1)
     

mylist1 = [3,4,2,3,5,1,2,4,1,2,3,4,2,3,3]
mylist1.sort()
removeduplicates(mylist1)

def GCDRecursion(a,b):
    if b == 0:
        return a 
    else:
        return GCDRecursion(b, a%b)

a = 10
b = 15
print("The GCD of", a, "and", b, "is:", GCDRecursion(a,b))

def destobynary(n):
    if n>1:
       destobynary(n//2)
       print(n%2, end = '')
    else:
        print(n, end = '')

n = 7
destobynary(n)



mylist2 = [(1, 2), (3, 1), (5, 0), (4, 3)]
mylist2.sort(key = lambda x: x[1])
print("The list after sorting on second element is:", mylist2)