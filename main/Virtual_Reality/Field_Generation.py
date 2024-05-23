# -*- coding: utf-8 -*-
"""
Created on Tue Dec 12 10:01:12 2023

@author: Janek
"""
import numpy as np
import os
import flopy
# from Virtual_Reality.functions.generator import gsgenerator
from dependencies.randomK_points import randomK_points
# from dependencies.plotting.plot_fields import plot_fields
# import sys 

def generate_fields(pars):
    #%% Field generation (based on Olafs Skript)
    # Watch out as first entry corresponds to y and not to x

    lx      = pars['lx']
    ang     = pars['ang']
    sigma   = pars['sigma']
    mu      = pars['mu']
    cov     = pars['cov']
    
    sim_ws = pars['sim_ws']
    mname = pars['mname']
    
    sim        = flopy.mf6.modflow.MFSimulation.load(
                            version             = 'mf6', 
                            exe_name            = 'mf6',
                            sim_ws              = sim_ws, 
                            verbosity_level     = 0
                            )
    
    gwf = sim.get_model(mname)
    mg = gwf.modelgrid
    cxy = np.vstack((mg.xyzcellcenters[0], mg.xyzcellcenters[1])).T
    dxmax      = np.max([max(sublist) - min(sublist) for sublist in mg.xvertices])
    dymax      = np.max([max(sublist) - min(sublist) for sublist in mg.yvertices])
    dx         = [dxmax, dymax]
   
    #%% Field generation
    Kflat, K  = randomK_points(mg.extent, cxy, dx,  lx[0], np.deg2rad(ang[0]), np.exp(sigma[0]), cov, np.exp(mu[0]), pars, random = False)
    Rflat, R = randomK_points(mg.extent, cxy, dx,  lx[1], np.deg2rad(ang[1]), sigma[1], cov, mu[1], pars, random = False)
    logK = np.log(K)
    # Anmerkung des Übersetzers: Beim generieren dieser Felder ist die Varianz per se dimensionslos
    # Wenn wir also die Felder von Erdal und Cirpka nachbilden wollen, müssen wir überhaupt nicht
    # die Varianz mitscalieren, wenn die Einheiten geändert werden, sonder nur der mean

    #%% Saving the fields - Übergabe in (m/s)
    np.savetxt(os.path.join(pars['k_r_d']), Kflat, delimiter = ',')
    np.savetxt(os.path.join(pars['r_r_d']), Rflat/1000/86400, delimiter = ',')

    return Kflat, Rflat/1000/86400, K, R