# -*- coding: utf-8 -*-
"""
Created on Tue Dec 12 10:01:12 2023

@author: Janek
"""
import numpy as np
import os
from cmcrameri import cm
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable

import flopy

# imports from parent directory
from dependencies.plot import plot_fields
from Virtual_Reality.functions.generator import gsgenerator

def generate_fields(pars):
    #%% Field generation (based on Olafs Skript)
    # Watch out as first entry corresponds to y and not to x
    
    nx      = pars['nx']
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
    # xyz = mg.xyzcellcenters
    cxy = np.vstack((mg.xyzcellcenters[0], mg.xyzcellcenters[1])).T
    dxmin           = np.min([max(sublist) - min(sublist) for sublist in mg.xvertices])
    dymin           = np.min([max(sublist) - min(sublist) for sublist in mg.yvertices])
    dx         = [dxmin, dymin]
    # xyzip = list(zip(xyz[0], xyz[1]))
    
    
    #%% Field generation (based on gstools)
    
    logK    = gsgenerator(gwf, pars,lx[0], ang[0], sigma[0],  cov, random = False) 
    logK        = logK.T + mu[0]    # [log(m/s)]
    rech    = gsgenerator(gwf, pars, lx[1], ang[1], sigma[1],  cov, random = False) 
    rech        = (rech.T + mu[1])  # [mm/d]
    
    # TODO: fix this at some other time
    # K = randomK_points(mg.extent, cxy, dx,  lx[0], np.deg2rad(ang[0]), sigma[0], cov, mu[0], random = False)
    # R = randomK_points(mg.extent, cxy, dx,  lx[1], np.deg2rad(ang[1]), sigma[1], cov, mu[1], random = False)
    # K = np.exp(K)
    # Anmerkung des Übersetzers: Beim generieren dieser Felder ist die Varianz per se dimensionslos
    # Wenn wir also die Felder von Erdal und Cirpka nachbilden wollen, müssen wir überhaupt nicht
    # die Varianz mitscalieren, wenn die Einheiten geändert werden, sonder nur der mean
    inspection = True
    if inspection:
        # plt.scatter(xyz[0], xyz[1], c=logK)
        # plt.show()
        
        plot_fields(gwf, pars, np.exp(logK), rech)
    #%% plotting
    
    print(mu)
    print(np.mean(logK), np.mean(rech))
    #%% Saving the fields - Übergabe in (m/s)
    np.savetxt(os.path.join(pars['k_r_d']), np.exp(logK), delimiter = ',')
    np.savetxt(os.path.join(pars['r_r_d']), rech/1000/86400, delimiter = ',')

# import sys
# sys.path.append('..')
# from dependencies.randomK_points import randomK_points
# from dependencies.model_params import get
# pars = get()
# generate_fields(pars)