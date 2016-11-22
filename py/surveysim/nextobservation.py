import numpy as np
import astropy.io.fits as pyfits
from surveysim.exposurecalc import airMassCalculator
from surveysim.utils import mjd2lst
from astropy.time import Time
from desitarget.targetmask import obsconditions as obsbits

MAX_AIRMASS = 10.0 #3.0 This new bound effectively does nothing.
MIN_MOON_SEP = 90.0
MIN_MOON_SEP_BGS = 5.0

def nextFieldSelector(obsplan, mjd, conditions, tilesObserved, slew, previous_ra, previous_dec, use_jpl=False):
    """
    Returns the first tile for which the current time falls inside
    its assigned LST window and is far enough from the Moon and
    planets.

    Args:
        obsplan: string, FITS file containing the afternoon plan
        mjd: float, current time
        conditions: dictionnary containing the weather info
        tilesObserved: list containing the tileID of all completed tiles
        slew: bool, True if a slew time needs to be taken into account
        previous_ra: float, ra of the previous observed tile (degrees)
        previous_dec: float, dec of the previous observed tile (degrees)
        use_jpl: bool, True if using jplephem and astropy instead of pyephem

    Returns:
        target: dictionnary containing the following keys:
                'tileID', 'RA', 'DEC', 'Program', 'Ebmv', 'maxLen',
                'MoonFrac', 'MoonDist', 'MoonAlt', 'DESsn2', 'Status',
                'Exposure', 'obsSN2', 'obsConds'
        overhead: float (seconds)
    """
    if (use_jpl):
        from desisurvey.avoidobjectJPL import avoidObject, moonLoc
    else:
        from surveysim.avoidobject import avoidObject, moonLoc

    hdulist = pyfits.open(obsplan)
    tiledata = hdulist[1].data
    moonfrac = hdulist[0].header['MOONFRAC']
    tileID = tiledata['TILEID']
    tmin = tiledata['LSTMIN']
    tmax = tiledata['LSTMAX']
    explen = tiledata['MAXEXPLEN']/240.0
    ra = tiledata['RA']
    dec = tiledata['DEC']
    program = tiledata['PROGRAM']
    obsconds = tiledata['OBSCONDITIONS']

    lst = mjd2lst(mjd)
    dt = Time(mjd, format='mjd')
    found = False
    for i in range(len(tileID)):
        dra = np.abs(ra[i]-previous_ra)
        if dra > 180.0:
            dra = 360.0 - dra
        ddec = np.abs(dec[i]-previous_dec)
        overhead = setup_time(slew, dra, ddec)
        t1 = tmin[i] + overhead/240.0
        t2 = tmax[i] - explen[i]

        if ( ((t1 <= t2) and (lst > t1 and lst < t2)) or ( (t2 < t1) and ((lst > t1 and t1 <=360.0) or (lst >= 0.0 and lst < t2))) ):
            if (avoidObject(dt, ra[i], dec[i]) and airMassCalculator(ra[i], dec[i], lst) < MAX_AIRMASS):
                moondist, moonalt, moonaz = moonLoc(dt, ra[i], dec[i])
                if ( (len(tilesObserved) > 0 and tileID[i] not in tilesObserved['TILEID']) or len(tilesObserved) == 0 ):
                    if (( (moonalt < 0.0 and (obsconds[i] & obsbits.mask('DARK')) != 0) ) or
                         (moonalt >=0.0 and
                         (( (moonfrac < 0.2 or (moonalt*moonfrac < 12.0)) and moondist > MIN_MOON_SEP and (obsconds[i] & obsbits.mask('GRAY')) != 0 ) or
                         ( (obsconds[i] & obsbits.mask('BRIGHT')) != 0 and moondist > MIN_MOON_SEP_BGS) ))):
                        found = True
                        break

    if found == True:
        tileID = tiledata['TILEID'][i]
        RA = ra[i]
        DEC = dec[i]
        Ebmv = tiledata['EBV_MED'][i]
        maxLen = tiledata['MAXEXPLEN'][i]
        DESsn2 = 100.0 # Some made-up number -> has to be the same as the reference in exposurecalc.py
        status = tiledata['STATUS'][i]
        exposure = -1.0 # Updated after observation
        obsSN2 = -1.0   # Idem
        target = {'tileID' : tileID, 'RA' : RA, 'DEC' : DEC, 'Program': program[i], 'Ebmv' : Ebmv, 'maxLen': maxLen,
                  'MoonFrac': moonfrac, 'MoonDist': moondist, 'MoonAlt': moonalt, 'DESsn2': DESsn2, 'Status': status,
                  'Exposure': exposure, 'obsSN2': obsSN2, 'obsConds': obsconds[i]}
    else:
        target = None
    return target, overhead

def setup_time(slew, dra, ddec):
    """
    Computes setup time: slew and focus (assumes readout can proceed during
    slew.

    Args:
        slew: bool, True if slew time needs to be taken into account
        dra: float, difference in RA between previous and current tile (degrees)
        ddec: float, difference in DEC between previous and current tile (degrees)

    Returns:
        float, total setup time (seconds)
    """

    focus_time = 30.0
    slew_time = 0.0
    if slew:
        d = np.maximum(dra, ddec)
        slew_time = 11.5 + d/0.45
    overhead = focus_time + slew_time
    if overhead < 120.0:
        overhead = 120.0
    return overhead
