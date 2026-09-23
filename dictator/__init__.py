"""Dictator: hold a key, talk, and the words land where your cursor is.

As a library:

    from dictator import Dictator

    d = Dictator()
    said = d.transcribe("recording.wav")
    print(said.text)

`Dictator`, `Transcript`, `transcribe` and `VERSION` are the public surface.
Everything else in this package is internal and will move without warning.
"""
from .api import VERSION, Dictator, Transcript, transcribe

__all__ = ["Dictator", "Transcript", "transcribe", "VERSION"]
