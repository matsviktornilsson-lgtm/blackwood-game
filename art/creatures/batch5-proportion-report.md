# Batch 5 werewolf proportions

The Batch 5 rig and the game puppet have substantially different rest poses and segment lengths. The current close-up driver copies the puppet’s world position to every skin joint, so a direct swap would stretch the new skin, especially between elbow and wrist.

## Joint positions

The puppet was instantiated through `createWolf()` before its first animation frame, with its root at the origin and rotation set to identity. Joint positions come from the exact objects used by the close-up driver. The Batch 5 positions come from the exported GLB joint hierarchy. Both use centimeters in game coordinates (X right, Y up, −Z forward). Δ is Batch 5 minus puppet. The same measurement on the shipped v1 GLB matched the puppet at all 19 joints to within 0.01 cm.

| Joint | Puppet X, Y, Z | Batch 5 X, Y, Z | Δ X, Y, Z | Distance |
| --- | ---: | ---: | ---: | ---: |
| Chest | 0.0, 113.0, 23.2 | 2.9, 146.0, 3.8 | 2.9, 33.0, -19.4 | 38.4 |
| Pelvis | 0.0, 110.6, 41.9 | -0.1, 114.0, 14.6 | -0.1, 3.4, -27.3 | 27.5 |
| Head | 0.0, 170.5, -61.2 | 3.0, 193.0, -20.9 | 3.0, 22.5, 40.3 | 46.3 |
| Jaw | 0.0, 162.2, -56.5 | 3.0, 188.1, -27.8 | 3.0, 25.9, 28.7 | 38.8 |
| Tail | 0.0, 109.0, 70.6 | 1.8, 112.0, 26.4 | 1.8, 3.0, -44.2 | 44.3 |
| Shoulder.L | -34.2, 163.7, -17.7 | -21.7, 179.0, -4.3 | 12.5, 15.3, 13.4 | 23.9 |
| Elbow.L | -48.6, 117.8, -12.9 | -27.0, 151.0, 11.8 | 21.6, 33.2, 24.7 | 46.7 |
| Wrist.L | -48.6, 53.7, -37.6 | -39.1, 123.0, -8.1 | 9.5, 69.3, 29.5 | 75.9 |
| Hip.L | -22.9, 110.6, 41.9 | -10.8, 112.0, 13.1 | 12.1, 1.4, -28.8 | 31.3 |
| Knee.L | -34.9, 70.6, 20.1 | -16.0, 71.3, -13.0 | 18.9, 0.7, -33.1 | 38.1 |
| Hock.L | -38.4, 32.7, 58.4 | -19.4, 19.4, 11.1 | 19.0, -13.3, -47.3 | 52.7 |
| Toes.L | -34.9, 6.2, 35.0 | -26.0, 4.7, -12.0 | 8.9, -1.5, -47.0 | 47.9 |
| Shoulder.R | 34.2, 163.7, -17.7 | 27.9, 179.0, -5.1 | -6.3, 15.3, 12.6 | 20.8 |
| Elbow.R | 48.6, 117.8, -12.9 | 36.7, 149.0, 4.8 | -11.9, 31.2, 17.7 | 37.8 |
| Wrist.R | 48.6, 53.7, -37.6 | 41.8, 124.0, -14.9 | -6.8, 70.3, 22.7 | 74.2 |
| Hip.R | 22.9, 110.6, 41.9 | 15.0, 112.0, 15.0 | -7.9, 1.4, -26.9 | 28.1 |
| Knee.R | 34.9, 70.6, 20.1 | 18.8, 66.0, -0.5 | -16.1, -4.6, -20.6 | 26.5 |
| Hock.R | 38.4, 32.7, 58.4 | 23.9, 18.0, 29.8 | -14.5, -14.7, -28.6 | 35.3 |
| Toes.R | 34.9, 6.2, 35.0 | 29.6, 4.5, 4.7 | -5.3, -1.7, -30.3 | 30.8 |

## Segment lengths

These are straight-line distances between joint centers. They measure the geometry the puppet drives regardless of where the character origin sits.

| Segment | Puppet (cm) | Batch 5 (cm) | Change if driven directly |
| --- | ---: | ---: | ---: |
| Chest → Head | 102.1 | 53.1 | +92.3% |
| Head → Jaw | 9.5 | 8.5 | +12.7% |
| Pelvis → Tail | 28.7 | 12.1 | +137.3% |
| Shoulder.L → Elbow.L | 48.3 | 32.7 | +47.7% |
| Elbow.L → Wrist.L | 68.7 | 36.4 | +88.7% |
| Hip.L → Knee.L | 47.1 | 48.6 | -3.1% |
| Knee.L → Hock.L | 54.0 | 57.3 | -5.8% |
| Hock.L → Toes.L | 35.5 | 28.2 | +25.9% |
| Shoulder.R → Elbow.R | 48.3 | 32.8 | +47.5% |
| Elbow.R → Wrist.R | 68.7 | 32.2 | +113.3% |
| Hip.R → Knee.R | 47.1 | 48.7 | -3.2% |
| Knee.R → Hock.R | 54.0 | 57.0 | -5.3% |
| Hock.R → Toes.R | 35.5 | 29.1 | +22.0% |

The combined upper-arm and forearm length is 117.0 cm per side on the puppet, compared with 69.1 cm on Batch 5’s left and 65.0 cm on its right. These sums are upper bounds on reach from the shoulder. The elbow-to-wrist spans would have to grow by about 89% and 113% respectively to match the puppet. The largest displacement from each model’s origin is at the left wrist (75.9 cm).

## Recommendation

Choose **B: adapt the generated rig and skin**. Fit the bind pose to the puppet’s contact joints, paying particular attention to the elbows, wrists and hand geometry. Fit the head and torso in the same pass and rebuild the skin binding from the fitted pose. The size of the forearm difference calls for a visual review of the fitted skin before integrating it. Moving only the bones would leave the deformation visible.

Option A would shorten the puppet’s maximum arm reach by roughly 48–52 cm if its dimensions were copied from Batch 5. The climb solver clamps targets to that reach, so changing those dimensions can move the wrists off the existing rock holds. With option B, the existing puppet still drives the climb and lunge. The visual acceptance check should cover both hands at the lip, the release into the lunge, and the landing in all three lanes. The Phase 1 jaw topology limitation also remains visible in close shots.

Phase 2 records the measurements and recommendation. The rig and game await the choice of approach.
