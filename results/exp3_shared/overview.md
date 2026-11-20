# Experiment 3 stress overview

Each condition changes one factor from the baseline. Means over seeds and failure modes. Broadcasts count rounds until the allocation stops changing; the total with the stopping rule's quiet rounds is in each condition's summary.

Flags: **unassigned** assigned-task rate < 1; **no-consensus** some run ended without all robots agreeing; **duplicates** a task claimed twice; **score-loss** mean score > 1% below the best method; **rarely-local** scoped method recovers locally in < 50% of runs.

| condition | robots | method | broadcasts | rounds | assigned | score | makespan s | shared busy s | local rate | consensus | flags |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline | 6 | Standard CBBA | 18.9 | 3.8 | 0.964 | 1193.9 | 58.3 | 44.4 | - | 1.00 | unassigned |
| baseline | 6 | ED-CBBA | 13.7 | 3.8 | 0.964 | 1193.9 | 58.3 | 44.4 | - | 1.00 | unassigned |
| baseline | 6 | Scoped ED-CBBA (40 m) | 14.2 | 4.1 | 0.964 | 1193.9 | 58.3 | 44.4 | 0.02 [0.00, 0.09] | 1.00 | unassigned, rarely-local |
| baseline | 12 | Standard CBBA | 49.3 | 4.5 | 1.000 | 2655.6 | 51.4 | 88.8 | - | 1.00 | - |
| baseline | 12 | ED-CBBA | 38.1 | 4.5 | 1.000 | 2655.6 | 51.4 | 88.8 | - | 1.00 | - |
| baseline | 12 | Scoped ED-CBBA (40 m) | 35.2 | 5.3 | 1.000 | 2653.4 | 52.7 | 89.2 | 0.28 [0.19, 0.41] | 1.00 | rarely-local |
| baseline | 24 | Standard CBBA | 105.4 | 4.6 | 1.000 | 5560.1 | 46.7 | 175.9 | - | 1.00 | - |
| baseline | 24 | ED-CBBA | 82.3 | 4.6 | 1.000 | 5560.1 | 46.7 | 175.9 | - | 1.00 | - |
| baseline | 24 | Scoped ED-CBBA (40 m) | 53.6 | 5.2 | 1.000 | 5556.3 | 48.1 | 175.9 | 0.65 [0.52, 0.76] | 1.00 | - |
| mid_mission | 6 | Standard CBBA | 15.2 | 3.0 | 1.000 | 1270.8 | 58.9 | 44.1 | - | 1.00 | - |
| mid_mission | 6 | ED-CBBA | 10.0 | 3.0 | 1.000 | 1270.8 | 58.9 | 44.1 | - | 1.00 | - |
| mid_mission | 6 | Scoped ED-CBBA (40 m) | 7.8 | 2.7 | 1.000 | 1269.2 | 59.7 | 43.9 | 0.38 [0.27, 0.51] | 1.00 | rarely-local |
| mid_mission | 12 | Standard CBBA | 37.0 | 3.4 | 1.000 | 2712.6 | 49.2 | 87.5 | - | 1.00 | - |
| mid_mission | 12 | ED-CBBA | 26.0 | 3.4 | 1.000 | 2712.6 | 49.2 | 87.5 | - | 1.00 | - |
| mid_mission | 12 | Scoped ED-CBBA (40 m) | 13.0 | 3.0 | 1.000 | 2710.3 | 50.6 | 87.7 | 0.75 [0.63, 0.84] | 1.00 | - |
| mid_mission | 24 | Standard CBBA | 81.7 | 3.5 | 1.000 | 5612.5 | 45.9 | 174.4 | - | 1.00 | - |
| mid_mission | 24 | ED-CBBA | 58.6 | 3.5 | 1.000 | 5612.5 | 45.9 | 174.4 | - | 1.00 | - |
| mid_mission | 24 | Scoped ED-CBBA (40 m) | 21.5 | 3.1 | 1.000 | 5609.9 | 46.9 | 174.7 | 0.87 [0.76, 0.93] | 1.00 | - |
| range_limited | 6 | Standard CBBA | 27.3 | 5.5 | 0.964 | 1193.5 | 58.4 | 44.2 | - | 1.00 | unassigned |
| range_limited | 6 | ED-CBBA | 19.7 | 5.5 | 0.964 | 1193.5 | 58.4 | 44.2 | - | 1.00 | unassigned |
| range_limited | 6 | Scoped ED-CBBA (40 m) | 20.1 | 5.8 | 0.964 | 1193.5 | 58.4 | 44.2 | 0.02 [0.00, 0.09] | 1.00 | unassigned, rarely-local |
| range_limited | 12 | Standard CBBA | 92.4 | 8.4 | 1.000 | 2655.6 | 51.4 | 88.8 | - | 1.00 | - |
| range_limited | 12 | ED-CBBA | 68.5 | 8.4 | 1.000 | 2655.6 | 51.4 | 88.8 | - | 1.00 | - |
| range_limited | 12 | Scoped ED-CBBA (40 m) | 64.2 | 9.0 | 1.000 | 2654.0 | 52.3 | 88.9 | 0.18 [0.11, 0.30] | 1.00 | rarely-local |
| range_limited | 24 | Standard CBBA | 237.7 | 10.3 | 1.000 | 5560.1 | 46.7 | 175.9 | - | 1.00 | - |
| range_limited | 24 | ED-CBBA | 180.8 | 10.3 | 1.000 | 5560.1 | 46.7 | 175.9 | - | 1.00 | - |
| range_limited | 24 | Scoped ED-CBBA (40 m) | 117.2 | 9.6 | 1.000 | 5557.2 | 47.6 | 175.8 | 0.55 [0.42, 0.67] | 1.00 | - |
| clustered | 6 | Standard CBBA | 19.8 | 4.0 | 0.987 | 1225.4 | 52.5 | 45.7 | - | 1.00 | unassigned |
| clustered | 6 | ED-CBBA | 14.5 | 4.0 | 0.987 | 1225.4 | 52.5 | 45.7 | - | 1.00 | unassigned |
| clustered | 6 | Scoped ED-CBBA (40 m) | 15.3 | 4.7 | 0.987 | 1225.2 | 52.8 | 45.7 | 0.05 [0.02, 0.14] | 1.00 | unassigned, rarely-local |
| clustered | 12 | Standard CBBA | 51.1 | 4.7 | 1.000 | 2648.5 | 46.9 | 87.8 | - | 1.00 | - |
| clustered | 12 | ED-CBBA | 40.0 | 4.7 | 1.000 | 2648.5 | 46.9 | 87.8 | - | 1.00 | - |
| clustered | 12 | Scoped ED-CBBA (40 m) | 35.9 | 5.8 | 1.000 | 2646.0 | 47.8 | 88.3 | 0.38 [0.27, 0.51] | 1.00 | rarely-local |
| clustered | 24 | Standard CBBA | 103.9 | 4.5 | 1.000 | 5452.2 | 43.4 | 173.9 | - | 1.00 | - |
| clustered | 24 | ED-CBBA | 80.8 | 4.5 | 1.000 | 5452.2 | 43.4 | 173.9 | - | 1.00 | - |
| clustered | 24 | Scoped ED-CBBA (40 m) | 53.1 | 5.2 | 1.000 | 5448.9 | 44.4 | 174.5 | 0.73 [0.61, 0.83] | 1.00 | - |
| imbalanced | 6 | Standard CBBA | 19.8 | 4.0 | 0.939 | 1162.8 | 57.0 | 52.0 | - | 1.00 | unassigned |
| imbalanced | 6 | ED-CBBA | 14.5 | 4.0 | 0.939 | 1162.8 | 57.0 | 52.0 | - | 1.00 | unassigned |
| imbalanced | 6 | Scoped ED-CBBA (40 m) | 13.2 | 4.1 | 0.940 | 1162.7 | 57.4 | 52.1 | 0.20 [0.12, 0.32] | 1.00 | unassigned, rarely-local |
| imbalanced | 12 | Standard CBBA | 46.2 | 4.2 | 0.903 | 2440.8 | 51.5 | 110.2 | - | 1.00 | unassigned |
| imbalanced | 12 | ED-CBBA | 35.1 | 4.2 | 0.903 | 2440.8 | 51.5 | 110.2 | - | 1.00 | unassigned |
| imbalanced | 12 | Scoped ED-CBBA (40 m) | 32.4 | 5.0 | 0.904 | 2439.9 | 51.9 | 110.3 | 0.30 [0.20, 0.43] | 1.00 | unassigned, rarely-local |
| imbalanced | 24 | Standard CBBA | 96.6 | 4.2 | 0.910 | 5115.9 | 50.0 | 217.4 | - | 1.00 | unassigned |
| imbalanced | 24 | ED-CBBA | 73.6 | 4.2 | 0.910 | 5115.9 | 50.0 | 217.4 | - | 1.00 | unassigned |
| imbalanced | 24 | Scoped ED-CBBA (40 m) | 63.8 | 5.3 | 0.910 | 5114.9 | 50.0 | 217.4 | 0.42 [0.30, 0.54] | 1.00 | unassigned, rarely-local |
| double_failure | 6 | Standard CBBA | 14.5 | 3.6 | 0.837 | 1008.6 | 59.6 | 45.8 | - | 1.00 | unassigned |
| double_failure | 6 | ED-CBBA | 10.3 | 3.6 | 0.837 | 1008.6 | 59.6 | 45.8 | - | 1.00 | unassigned |
| double_failure | 6 | Scoped ED-CBBA (40 m) | 10.3 | 3.6 | 0.837 | 1008.6 | 59.6 | 45.8 | 0.00 [0.00, 0.06] | 1.00 | unassigned, rarely-local |
| double_failure | 12 | Standard CBBA | 49.7 | 5.0 | 0.984 | 2541.7 | 56.3 | 92.2 | - | 1.00 | unassigned |
| double_failure | 12 | ED-CBBA | 39.4 | 5.0 | 0.984 | 2541.7 | 56.3 | 92.2 | - | 1.00 | unassigned |
| double_failure | 12 | Scoped ED-CBBA (40 m) | 39.5 | 5.0 | 0.984 | 2541.7 | 56.3 | 92.2 | 0.00 [0.00, 0.06] | 1.00 | unassigned, rarely-local |
| double_failure | 24 | Standard CBBA | 110.0 | 5.0 | 1.000 | 5486.4 | 49.3 | 177.1 | - | 1.00 | - |
| double_failure | 24 | ED-CBBA | 87.9 | 5.0 | 1.000 | 5486.4 | 49.3 | 177.1 | - | 1.00 | - |
| double_failure | 24 | Scoped ED-CBBA (40 m) | 87.7 | 5.1 | 1.000 | 5486.3 | 49.4 | 177.1 | 0.02 [0.00, 0.09] | 1.00 | rarely-local |
| cascading | 6 | Standard CBBA | 33.1 | 7.3 | 0.870 | 1037.7 | 61.4 | 41.0 | - | 1.00 | unassigned |
| cascading | 6 | ED-CBBA | 23.6 | 7.3 | 0.870 | 1037.7 | 61.4 | 41.0 | - | 1.00 | unassigned |
| cascading | 6 | Scoped ED-CBBA (40 m) | 24.2 | 7.8 | 0.870 | 1037.7 | 61.4 | 41.0 | 0.00 [0.00, 0.11] | 1.00 | unassigned, rarely-local |
| cascading | 12 | Standard CBBA | 95.3 | 9.1 | 0.981 | 2539.1 | 56.3 | 89.2 | - | 1.00 | unassigned |
| cascading | 12 | ED-CBBA | 73.7 | 9.1 | 0.981 | 2539.1 | 56.3 | 89.2 | - | 1.00 | unassigned |
| cascading | 12 | Scoped ED-CBBA (40 m) | 73.1 | 11.1 | 0.981 | 2539.6 | 56.2 | 89.2 | 0.13 [0.05, 0.30] | 1.00 | unassigned, rarely-local |
| cascading | 24 | Standard CBBA | 201.7 | 9.0 | 1.000 | 5492.7 | 50.0 | 174.3 | - | 1.00 | - |
| cascading | 24 | ED-CBBA | 156.5 | 9.0 | 1.000 | 5492.7 | 50.0 | 174.3 | - | 1.00 | - |
| cascading | 24 | Scoped ED-CBBA (40 m) | 110.7 | 10.7 | 1.000 | 5490.2 | 50.4 | 174.8 | 0.40 [0.25, 0.58] | 1.00 | rarely-local |
