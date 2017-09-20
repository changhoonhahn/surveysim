#!/bin/bash
#############################################################################
# Simulate the baseline survey strategy described in DESI-doc-1767-v3.
# Note that this is one random realization of the observing conditions.
# Change the random seed for a different realization.
# This will take ~4 hours to run and writes ~5.1G to $DESISURVEY.
# For a visualization of this simulation (created with surveymovie) see
# https://www.youtube.com/watch?v=vO1QZD_aCIo
#############################################################################

PLAN_ARGS='--verbose'
SIM_ARGS='--verbose --scores --seed 123 --stop 2024-11-30 --strategy HA+fallback'

surveyinit --verbose
surveyplan --create ${PLAN_ARGS}
surveysim ${SIM_ARGS}

while :
do
    (surveyplan ${PLAN_ARGS}) || break
    (surveysim --resume ${SIM_ARGS}) || break
done