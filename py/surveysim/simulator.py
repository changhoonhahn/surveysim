"""Top-level survey simulation manager.
"""
from __future__ import print_function, division, absolute_import

import datetime

import numpy as np

import astropy.table
import astropy.time
import astropy.units as u

import desiutil.log

import desisurvey.ephemerides
import desisurvey.afternoonplan
import desisurvey.schedule
import desisurvey.plan
import desisurvey.utils
import desisurvey.config

import surveysim.nightops
import surveysim.weather


class Simulator(object):
    """Initialize a survey simulation.

    Parameters
    ----------
    start_date : datetime.date
        Survey starts on the evening of this date.
    stop_date : datetime.date
        Survey stops on the morning of this date.
    progress : desisurvey.progress.Progress
        Progress of survey at the start of this simulation.
    weather : surveysim.weather.Weather
        Simulated weather conditions use use.
    stats : astropy.table.Table
        Table of per-night efficiency statistics to update.
    strategy : str
        Strategy to use for scheduling tiles during each night.
    plan : str or None
        Name of plan file to use. Required unless strategy is 'baseline'.
    gen : numpy.random.RandomState or None
        Random number generator to use for reproducible samples. Will be
        initialized (un-reproducibly) if None.
    computeHA : bool
        ?
    """
    def __init__(self, start_date, stop_date, progress, weather, stats,
                 strategy='baseline', plan=None, gen=None,
                 computeHA=False):
        self.log = desiutil.log.get_logger()
        self.config = desisurvey.config.Configuration()

        # Validate date range.
        if start_date >= stop_date:
            raise ValueError('Expected start_date < stop_date.')
        if (start_date < self.config.first_day() or
            stop_date > self.config.last_day()):
            raise ValueError('Cannot simulate beyond nominal survey dates.')
        self.start_date = start_date
        self.stop_date = stop_date
        self.last_index = (self.stop_date - self.config.first_day()).days

        # Tabulate sun and moon ephemerides for each night of the survey.
        self.ephem = desisurvey.ephemerides.Ephemerides(use_cache=True)

        if strategy == 'baseline':
            # Build the survey plan.
            self.sp = desisurvey.afternoonplan.surveyPlan(
                self.ephem.start.mjd, self.ephem.stop.mjd, self.ephem,
                computeHA)
        else:
            # Load the survey scheduler to use.
            self.sp = desisurvey.schedule.Scheduler()
        self.strategy = strategy

        self.gen = gen
        self.weather = weather

        if plan is not None:
            # Load the plan to use.
            self.plan = astropy.table.Table.read(self.config.get_path(plan))
            assert np.all(self.sp.tiles['tileid'] == self.plan['tileid'])
        else:
            self.plan = None

        if len(stats) != (self.config.last_day() - self.config.first_day()).days:
            raise ValueError('Input stats table has wrong length.')
        self.stats = stats

        self.day_index = (self.start_date - self.config.first_day()).days
        self.survey_done = False
        self.completed = progress.completed()
        self.progress = progress
        self.log.info(
            'Will simulate {0} to {1} with {2:.1f} / {3} tiles completed.'
            .format(start_date, stop_date, self.completed, progress.num_tiles))

    @property
    def date(self):
        """The current simulation date as a datetime object.
        """
        return self.config.first_day() + datetime.timedelta(days=self.day_index)

    def next_day(self):
        """Simulate the next day of survey operations.

        A day runs from local noon to local noon. A survey ends, with
        this method returning False, when either we reach the last
        scheduled day or else we run out of tiles to observe.

        Returns
        -------
        bool
            True if there are more days to simulate.
        """
        if self.day_index >= self.last_index or self.survey_done:
            return False

        date = self.date
        self.log.info('Simulating {0}'.format(date))

        if desisurvey.utils.is_monsoon(date):
            self.log.info('No observing during monsoon.')
        elif self.ephem.is_full_moon(date):
            self.log.info('No observing during full moon.')
        else:

            # Each day of observing starts at local noon.
            local_noon = desisurvey.utils.local_noon_on_date(date)

            # Lookup tonight's ephemerides.
            night = self.ephem.get_night(date)

            if self.strategy == 'baseline':
                # Create the afternoon plan.
                obsplan = self.sp.afternoonPlan(night, self.progress)
            else:
                # Use the global planner.
                obsplan = self.sp

            # Simulate tonight's observing.
            totals = surveysim.nightops.nightOps(
                night, obsplan, self.weather, self.progress, self.strategy,
                self.plan, self.gen)

            # Update our efficiency tracker.
            for mode in totals:
                self.stats[mode][self.day_index] = totals[mode].to(u.day).value

            # Progress report.
            completed = self.progress.completed()
            self.log.info('Completed {0:.1f} tiles tonight.'
                          .format(completed - self.completed))
            self.completed = completed

            # Are we done yet?
            if self.plan:
                # Have we completed a group so that we need to update the plan?
                self.survey_done = desisurvey.plan.update_required(
                    self.plan, self.progress)
            else:
                # With no plan, keep going until all tiles are observed.
                if self.progress.num_tiles - completed < 0.1:
                    self.survey_done = True

        self.day_index += 1
        if self.day_index == self.last_index:
            self.survey_done = True

        return not self.survey_done