import numpy as np
from scipy.interpolate import griddata

def randomK_points(extent, cxy, dx,  lx, ang, sigY, pars, random = True, ftype = []):
    '''
    Generate auto-correlated 2-D random hydraulic-conductivity fields using
    spectral methods.
    An extended periodic field is generated and the domain of interest is cut
    out.
    Parameters
    ----------
    coordinates: coordinates of the cell mid points
    lx (1x2)   : correlation length [m] in longitudinal/transverse direction
    ang (1x1)  : rotation angle [radians] of the covariance function
    sigY (1x1) : variance of ln(K) [K in m/s]
    Kg : geometric mean of hydraulic conductivity [m/s]


    Returns
    K          : Field of hydraulic Conductivity

    '''
        
    if not random:
        if ftype == 'K':
            Kg = np.exp(pars['mu'][0])
        elif ftype == 'R':
            Kg = pars['mu'][1]
        if pars['cov'] == 'Exponential':
            # Good choice for Exponential
            np.random.seed(6)
        elif pars['cov'] == 'Matern':
            if pars['l_red'] == 1:
                # Good choice for Matern 3/2
                np.random.seed(2)
            elif pars['l_red'] == 10:
                # Good choice for Matern 3/2 with l_red = 10
                np.random.seed(8)
            elif pars['l_red'] == 5:
                # Good choice for Matern 3/2 with l_red = 5
                np.random.seed(92)   
    else:
        Kg = pars['geomea']

    # total number of nodes
    ntot = len(cxy)
    xmin, xmax, ymin, ymax = extent

    nx = int(np.ceil((xmax - xmin)/dx[0]))
    ny = int(np.ceil((ymax - ymin)/dx[1]))
    
    nx_ex = np.round((np.array([xmax-xmin, ymax-ymin]) + 5*np.array(lx)) / dx).astype(int)
    nx_ex = [np.max(nx_ex), np.max(nx_ex)]

    
    x = np.arange(-(nx_ex[0] +1) / 2 * dx[0], (nx_ex[0] - 1) / 2 * dx[0] + dx[0], dx[0])
    y = np.arange((nx_ex[1] +1) / 2 * dx[1], -(nx_ex[1] - 1) / 2 * dx[1] + dx[1], -dx[1])

    xint = np.arange(xmin + dx[0]/2, xmax + dx[0]/2, dx[0])
    yint = np.arange(ymin + dx[1]/2, ymax + dx[1]/2, dx[1])
    Xint, Yint = np.meshgrid(xint, yint)
    
    # Grid in Physical Coordinates
    X, Y = np.meshgrid(x, y)
    # Y = np.flip(Y, axis = 0)
    X2, Y2 = pars['rot2df'](X, Y, ang)
    
    # Scaling by correlation lengths
    H = np.sqrt((X2/lx[0])**2+(Y2/lx[1])**2)
    # H = np.flip(H, axis = 0)
    
    RYY = pars['covmat'](H, sigY, pars['cov'])
       
    # ============== END AUTO-COVARIANCE BLOCK ================================
    
    # ============== BEGIN POWER-SPECTRUM BLOCK ===============================
    # Fourier Transform (Origin Shifted to Node (1,1))
    # Yields Power Spectrum of the field
    SYY = np.fft.fftn(np.fft.fftshift(RYY)) / ntot
    # Remove Imaginary Artifacts
    SYY = np.abs(SYY)
    SYY[0,0] = 0
    # ============== END POWER-SPECTRUM BLOCK =================================
    
    # ============== BEGIN FIELD GENERATION BLOCK =============================
    # Generate a field of random real numbers,
    # transform the field into the spectral domain,
    # and evaluate the corresponding phase-spectrum.
    # This random phase-spectrum and the given power spectrum
    # define the Fourier transform of the random autocorrelated field.
    shape = np.shape(SYY)
    ran = np.multiply(np.sqrt(SYY),
                      (np.random.randn(shape[0], shape[1]) +
                       1j * np.random.randn(shape[0], shape[1])))

    # Backtransformation into the physical coordinates
    K = Kg * np.exp(np.real(np.fft.ifftn(ran*ntot)))
    K = K[0:ny, 0:nx]
    
    # generating an associated grid for K 
    values_at_coordinates = griddata((Xint.ravel(), Yint.ravel()), K.ravel(),
                                     (cxy[:,0], cxy[:,1]), method='nearest')
    
    return values_at_coordinates, K