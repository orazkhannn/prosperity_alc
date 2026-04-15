Run the whole /datasets/round1/ bundle:
```
make round1 TRADER=traders/baha/baha-ash0.py
```

Start a single continuous carried run across all Round 1 days:
```
make round1 TRADER=traders/baha/baha-ash0.py CARRY=1
```

To run days separately:
```
make round1 TRADER=traders/baha/baha-ash0.py DAY=-2
make round1 TRADER=traders/baha/baha-ash0.py DAY=-1
make round1 TRADER=traders/baha/baha-ash0.py DAY=0
```

```
make submission ROUND=round# TRADER=traders/baha/baha-ash0.py
```
specifically runs the submission dataset for that round, when present.
