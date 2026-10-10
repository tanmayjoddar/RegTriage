#!/bin/bash
# Slurm batch template for RegTriage jobs.
# Mirror of src/regtriage/runner/slurm.py::_BATCH_TEMPLATE — keep in sync.
# Placeholders use @NAME@ style and are filled by operators, not by code.
#SBATCH --job-name=@JOB_ID@
#SBATCH --output=@STDOUT_PATH@
#SBATCH --error=@STDERR_PATH@
#SBATCH --time=@TIME_LIMIT@
#SBATCH --parsable

@COMMAND@
