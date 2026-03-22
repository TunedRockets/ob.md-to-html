
j = 5
l = ['0','1','2','3','4','5']
for i in range(j-1,2,-1):
    l.pop(i)
    j -=1
    print(f"{i=}, {j=}, {l[j]=}")
    