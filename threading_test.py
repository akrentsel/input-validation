
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED, FIRST_EXCEPTION
from time import sleep
from threading import Lock
from multiprocessing.pool import Pool
lock = Lock()
lock.acquire()
def a():
    for i in range(1, 10):
        print(i)
        sleep(1) # THIS DOES FUCKING WORK
    return 1
def b(lock):
    print("lols")
    lock.acquire()
    for i in range (100, 103):
        print(i)
        sleepa(3)
    lock.release()
    return 1

pool = ThreadPoolExecutor(max_workers=2)
d = pool.submit(b, lock)
c = pool.submit(a)
sleep(15)
lock.release()
print(wait([c, d], timeout=None, return_when=FIRST_EXCEPTION))
# takeaway: thread pools fail to implement efficient pool yielding during time.sleep or lock blocks