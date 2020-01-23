# -*- Encoding: UTF-8 -*-

from mpi4py import MPI 
#from mpi4py.futures import MPIPoolExecutor
import numpy as np 
import logging
import threading
import queue
import concurrent.futures
#import timeit

import attr
import time
import datetime


"""
Author: Ralph Kube

Mockup of Jong's Pool processing model with the addition of a global futures_list.
The queue consumer does not evaluate futures but appends them to a global futures_list.
The futures in that list are handled one-by-one as the results become available


To run on an interactive node

using MPIPoolExecutor
srun -n 4 python -m mpi4py.futures processor_mpi_nonblocking_mockup.py  --config configs/test_crossphase.json

using concurrent.futures.PoolExecutor:
python processor_mpi_nonblocking_mockup.py
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,%(msecs)d %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


@attr.s 
class AdiosMessage:
    """ Defines data chunks as read from adios."""
    tstep_idx = attr.ib(repr=True)
    data       = attr.ib(repr=False)


def calc(param, tidx, data):
    wait = np.random.uniform(0.0, 1.0)
    tstart = datetime.datetime.now()
    time.sleep(wait)
    #logging.info(f"     calc: tidx {tidx}, param = {param}")#", data = {data}")
    return (tidx, param, tstart, wait)


def consume(Q, executor, futures_list):
    while True:
        msg = Q.get()
        logging.info(f"Consuming message {msg}. Number of futures: {len(futures_list)}")
        if msg.tstep_idx == None:
            Q.task_done()
            break

        for future in [executor.submit(calc, param, msg.tstep_idx, msg.data) for param in range(5)]:
            #logging.info(f"     tstep = {msg.tstep_idx} res = {future.result()}")
            futures_list.append(future)

        logging.info(f"Done consuming {msg}.  Number of futures: {len(futures_list)}")
        Q.task_done()


def main():

    # Define a data queue. This serves as the connection between the receiver (datastream from KSTAR)
    # to the executor that handles the analysis routines
    dq = queue.Queue()
    msg = AdiosMessage(0, None)
    # Dummy data of the same shape as the DFT of a time-chunk.
    data = np.zeros([192, 512, 38], dtype=np.complex128)

    # Define an executor that handles the analysis tasks
    #executor = MPIPoolExecutor(max_workers=2)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=30)

    # This stores the list of all futures generated by the poolexecutor
    futures_list = []

    # Start a worker thread that pops element from the queue and dispatches it to
    # the executor
    worker = threading.Thread(target=consume, args=(dq, executor, futures_list))
    worker.start()

    # Start the receiver loop. Here we receive data chunks from remote
    for i in range(5):
        # Receive time chunk data
        logging.info(f"Received time chunk {i}")
        # Compile a message with the current data
        msg = AdiosMessage(tstep_idx=i, data=data)
        # Put the data in the queue
        dq.put(msg)

    logging.info("Finished the receiver loop")    
    # Put the hang-up message in the queue
    dq.put(AdiosMessage(None, None))
    # Close the queue
    dq.join()
    # Stop the worker process
    worker.join()

    # Finally, start processing the futures list
    for future in concurrent.futures.as_completed(futures_list):
        res = future.result()
        logging.info(f"Future completed: tidx={res[0]}, param={res[1]}, started at {res[2]}, wait={res[3]:6.4f}s")

    # Shutdown the MPIPoolExecutor
    # This has to be done after the queue has joined!
    executor.shutdown()


if __name__ == "__main__":
    main()



# End of file mpi_processor_mockup.py