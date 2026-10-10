# RegTriage infrastructure: single-node Slurm VM + NFS export

Every command below is exact and ordered. Each one is marked
NOT YET RUN BY A HUMAN until confirmed on the real VM.

## 1. Single-node Slurm VM (Ubuntu 24.04)

```bash
sudo apt-get update && sudo apt-get install -y slurm-wlm munge  # NOT YET RUN BY A HUMAN
sudo systemctl enable --now munge  # NOT YET RUN BY A HUMAN
```

Write `/etc/slurm/slurm.conf` (single node, local spool):

```text
ClusterName=regtriage
SlurmctldHost=localhost
NodeName=localhost CPUs=4 Boards=1 SocketsPerBoard=1 CoresPerSocket=4 ThreadsPerCore=1 State=UNKNOWN
PartitionName=debug Nodes=localhost Default=YES MaxTime=INFINITE State=UP
SlurmdSpoolDir=/var/spool/slurmd
```

```bash
sudo systemctl enable --now slurmctld slurmd  # NOT YET RUN BY A HUMAN
sinfo  # expect: partition debug, node localhost idle — NOT YET RUN BY A HUMAN
scontrol ping  # both daemons respond — NOT YET RUN BY A HUMAN
```

## 2. Service users and directories (different permissions)

```bash
sudo useradd --system --home /var/lib/regtriage --create-home regtriage  # NOT YET RUN BY A HUMAN
sudo useradd --system --no-create-home --shell /usr/sbin/nologin auditor  # NOT YET RUN BY A HUMAN
sudo mkdir -p /var/lib/regtriage /var/log/regtriage /srv/regtriage  # NOT YET RUN BY A HUMAN
sudo chown regtriage:regtriage /var/lib/regtriage /var/log/regtriage  # NOT YET RUN BY A HUMAN
```

## 3. NFS export with two permission levels

Server side (`/etc/exports`):

```text
/srv/regtriage 192.168.56.0/24(ro,sync,no_subtree_check) 192.168.56.10(rw,sync,no_subtree_check)
```

```bash
sudo exportfs -ra  # NOT YET RUN BY A HUMAN
sudo exportfs -v  # confirm both lines active — NOT YET RUN BY A HUMAN
setfacl -m u:regtriage:rwx /srv/regtriage  # NOT YET RUN BY A HUMAN
setfacl -m u:auditor:rx /srv/regtriage  # NOT YET RUN BY A HUMAN
getfacl /srv/regtriage  # regtriage:rwx, auditor:r-x — NOT YET RUN BY A HUMAN
```

Client side:

```bash
showmount -e nfs-server  # both exports visible — NOT YET RUN BY A HUMAN
sudo mount -t nfs nfs-server:/srv/regtriage /mnt/regtriage  # NOT YET RUN BY A HUMAN
sudo -u auditor touch /mnt/regtriage/probe && echo LEAK || echo "read-only holds"  # NOT YET RUN BY A HUMAN
```

## 4. API key file (mode 0600, root-owned)

```bash
sudo mkdir -p /etc/regtriage  # NOT YET RUN BY A HUMAN
printf 'ANTHROPIC_API_KEY=%s\n' "$KEY" | sudo tee /etc/regtriage/env >/dev/null  # NOT YET RUN BY A HUMAN
sudo chmod 0600 /etc/regtriage/env && sudo chown root:root /etc/regtriage/env  # NOT YET RUN BY A HUMAN
stat -c '%a %U:%G' /etc/regtriage/env  # expect: 600 root:root — NOT YET RUN BY A HUMAN
```

## 5. Install and enable the units

```bash
sudo cp deploy/regtriage.service deploy/regtriage.timer /etc/systemd/system/  # NOT YET RUN BY A HUMAN
sudo systemctl daemon-reload  # NOT YET RUN BY A HUMAN
sudo systemctl enable --now regtriage.timer  # NOT YET RUN BY A HUMAN
systemctl list-timers regtriage.timer  # NEXT run tomorrow — NOT YET RUN BY A HUMAN
sudo systemctl start regtriage.service  # one manual run — NOT YET RUN BY A HUMAN
sudo journalctl -u regtriage.service --no-pager | tail -20  # clusters=N line — NOT YET RUN BY A HUMAN
```

## 6. Slurm smoke test

```bash
sbatch --parsable deploy/sbatch-template.sh  # placeholder file rejected; use a rendered copy — NOT YET RUN BY A HUMAN
squeue --me  # job visible — NOT YET RUN BY A HUMAN
sacct -j <jobid> --format=JobID,State,ExitCode  # COMPLETED — NOT YET RUN BY A HUMAN
scancel <jobid>  # only if stuck — NOT YET RUN BY A HUMAN
```

Note: `deploy/sbatch-template.sh` holds `@PLACEHOLDERS@` and is documentation;
production scripts are rendered by `render_batch_script` (unit-tested).
