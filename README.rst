
source-query-proxy
==================

Credits
-------

Source Engine messages inspired by **Python-valve**
https://github.com/serverstf/python-valve

Prerequisites
-------------

Python 3.7 or above

You can use `pyenv <https://github.com/pyenv/pyenv>`_ to install any version of Python without root privileges

Installing
----------

.. code-block:: bash

    pip install source-query-proxy==1.0.0

Run
---

.. code-block:: bash

    sqproxy run


Run with eBPF
-------------

https://github.com/spumer/source-query-proxy-kernel-module/src-ebpf

1. Download eBPF script

    * Copy ``src-ebpf`` folder to target working directory

2. Install requirements https://github.com/spumer/source-query-proxy-kernel-module/src-ebpf/README.md

3. Enable eBPF in config (see examples/00-globals.yaml)

4. Run

    .. code-block:: bash

        sqproxy run


Development
-----------

.. code-block:: bash

    git clone https://github.com/spumer/source-query-proxy.git
    cd source-query-proxy
    poetry install
