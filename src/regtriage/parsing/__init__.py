"""Simulation log parsers: cocotb now, UVM and Verilator lint in Slice 10."""

from regtriage.parsing.base import Failure, Parser
from regtriage.parsing.cocotb import CocotbResultsParser

__all__ = ["CocotbResultsParser", "Failure", "Parser"]
