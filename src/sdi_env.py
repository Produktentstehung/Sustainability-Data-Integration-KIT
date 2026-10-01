# -*- coding: utf-8 -*-
"""Reads getting-started/.env into the environment.

Every script here takes its settings from environment variables, and until
this module existed only setup.py actually read the file. The others relied on
the variables already being in the environment, which is true when
start-nodered.ps1 put them there and false the moment somebody follows the
tutorial and types

    python ../src/run_chain.py

in a plain shell. They then fell back to their built-in defaults, silently.
That is harmless only as long as the defaults happen to be right. On an
installation where AAS_PORT was moved - which the KIT explicitly allows - the
scripts addressed a different server than the flows, and run_chain.py went as
far as importing the sample data into it and waiting for the flows to deliver
there. Nothing failed; it just watched the wrong machine.

Values already in the environment win, so a variable set on the command line
still overrides the file, and nothing changes for a caller that exports its
own settings.

Usage, before reading any SDI_* variable:

    from sdi_env import load_env
    load_env()
"""
import os

HIER = os.path.dirname(os.path.abspath(__file__))
# src/ and getting-started/ sit next to each other in the repository.
ENV_PFAD = os.path.join(os.path.dirname(HIER), "getting-started", ".env")


def load_env(pfad=None):
    """Put what .env holds into os.environ, without overwriting anything.

    Returns the path that was read, or None when there was no file - the
    caller can say so, rather than leaving the reader to wonder why a setting
    had no effect.
    """
    pfad = pfad or ENV_PFAD
    if not os.path.exists(pfad):
        return None
    with open(pfad, encoding="utf-8") as fh:
        for zeile in fh:
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            name, _, wert = zeile.partition("=")
            name, wert = name.strip(), wert.strip()
            if name and wert and name not in os.environ:
                os.environ[name] = wert
    return pfad
