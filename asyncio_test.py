
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED, FIRST_EXCEPTION
from time import sleep
from threading import Lock
import asyncio
from multiprocessing.pool import Pool
lock = Lock()
lock.acquire()
def a():
    for i in range(1, 10):
        print(i)
        sleep(1) # THIS DOES FUCKING WORK
    return 1
def b(lock):
    lock.acquire()
    for i in range (100, 103):
        print(i)
        sleep(3)
    lock.release()
    return 1

async def main():
    loop = asyncio.get_running_loop()

    # 2. Run in a custom thread pool:
    with ThreadPoolExecutor(num_workers=1) as pool:
        result = await loop.run_in_executor(
            pool, blocking_io)
        print('custom thread pool', result)

    # 3. Run in a custom process pool:
    with concurrent.futures.ProcessPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool, cpu_bound)
        print('custom process pool', result)

if __name__ == '__main__':
    asyncio.run(main())