
source-query-proxy
==================

Motivation
----------

Basically Source game-servers works in one thread and can't use more than one core for in-game logic.
For example - CS:GO, CS:Source, Left 4 Dead 2, etc.

Yes, you can use SourceMod to offload calculations (use threading), but we talking about common game logic.
E.g. you can try use `DoS Protection extension <https://forums.alliedmods.net/showpost.php?p=2518787&postcount=117>`_, but caching is not fast solution, cause server spent time to receiving and sending answer from cache.

This solution allow redirect some (A2S query) packets to backend and game server don't spent time to answer anymore.


IPTables (or any NAT) can't help!
---------------------------------

If you use IPTables (NAT) to redirect queries to proxy, this rule will be remembered in routing table and if client try to connect - connection will be redirected to proxy too.

We use right way to redirect - eBPF: https://github.com/sqproxy/sqredirect

Prerequisites
-------------

Python 3.7 or above

You can use `pyenv <https://github.com/pyenv/pyenv>`_ to install any version of Python without root privileges

Installing
----------

.. code-block:: bash

    pip install source-query-proxy==2.1.0

Configuring
-----------

sqproxy search configs in ``/etc/sqproxy/conf.d`` and ``./conf.d`` directories.
You should place your config files only in this directories.

For more info see `examples <examples/conf.d>`_

Run
---

.. code-block:: bash

    sqproxy run


Run with eBPF
-------------

Please read the instruction and install: https://github.com/sqproxy/sqredirect

1. Enable eBPF in config (see examples/00-globals.yaml)

2. Run

.. code-block:: bash

    sqproxy run


Development
-----------

.. code-block:: bash

    git clone https://github.com/spumer/source-query-proxy.git
    cd source-query-proxy
    poetry install
    

Credits
-------

Source Engine messages inspired by **Python-valve**
https://github.com/serverstf/python-valve

