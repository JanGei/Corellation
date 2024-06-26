#### 2-D random field generator
import numpy as np
import gstools as gs

class JibberishWarning(Warning):
    pass

def gsgenerator(gwf, pars,lx, ang, sigma, cov, mu = 0, covtype = [], valtype = [], random = True):
    
    dim = 2
    ang = np.deg2rad(ang)
    
    if covtype == 'random':
        lx = np.array([np.random.randint(50, lx[0]),
                       np.random.randint(50, lx[1])])
        ang = np.random.uniform(0, 2 * np.pi)
        sigma = np.random.uniform(1, 5)
        if lx[0] > lx[1]:
            lx = np.flip(lx)
            if ang > 0:
                ang -= np.pi/2
            else:
                ang += np.pi/2
        elif lx[0] == lx[1]:
            lx[0] += 1
    
    if cov == 'Matern':
        model = gs.Matern(dim=dim, var=sigma, angles = ang, len_scale=lx)
    elif cov == 'Exponential':
        model = gs.Exponential(dim = dim, var = sigma, len_scale=lx, angles = ang)
    elif cov == 'Gaussian':
        model = gs.Gaussian(dim = dim, var = sigma, len_scale=lx, angles = ang)
    else:
        raise JibberishWarning('You just entered a jibberish covariance model')
        
    modelgrid = gwf.modelgrid
    xyz = modelgrid.xyzcellcenters
    
    if random:
        srf = gs.SRF(model)
    else:
        if pars['cov'] == 'Exponential':
            # Good choice for Exponential
            srf = gs.SRF(model, seed=6)
        elif pars['cov'] == 'Matern':
            if pars['l_red'] == 1:
                # Good choice for Matern 3/2
                srf = gs.SRF(model, seed=12)
            elif pars['l_red'] == 10:
                # Good choice for Matern 3/2 with l_red = 10
                srf = gs.SRF(model, seed=8)
            elif pars['l_red'] == 5:
                # Good choice for Matern 3/2 with l_red = 5
                srf = gs.SRF(model, seed=44)
        
    field = srf.unstructured(([xyz[0],xyz[1]]))
    
    if valtype == 'good':
        field = np.exp(field.T + mu[0])
    elif valtype == 'random':
        mu = np.random.uniform(mu + mu/3, mu - mu/3)
        field = np.exp(field.T + mu[0])
    
    
    return field


def generator(nx, dx, lx, ang, sigma2, mu, cov, random = True):
    
    if random == False:
        np.random.seed(42)
        
    dimen   = 2
    ntot    = np.prod(nx[0:dimen])
    
    # ============== BEGIN COVARIANCE BLOCK ==========================================

    ang = np.radians(ang)
    # # Grid in Physical Coordinates
    
    x = np.arange(-nx[0] / 2 * dx[0], (nx[0] - 1) / 2 * dx[0] + dx[0], dx[0])
    y = np.arange(-nx[1] / 2 * dx[1], (nx[1] - 1) / 2 * dx[1] + dx[1], dx[1])
    # Grid in Physical Coordinates
    X, Y = np.meshgrid(x, y)
    
    # Rotation into Longitudinal/Transverse Coordinates
    X2 = np.cos(ang) * X + np.sin(ang) * Y
    Y2 = -np.sin(ang) * X + np.cos(ang) * Y
    

    H = np.sqrt((X2 / lx[0])**2 + (Y2 / lx[1])**2)

    # Matérn 3/2
    if cov == 'Matern':
        RYY = sigma2 * np.multiply((1+np.sqrt(3)*H), np.exp(-np.sqrt(3)*H))
    elif cov == 'Exponential':
        RYY = sigma2 * np.exp(-abs(H))
    elif cov == 'Gaussian':
        RYY = sigma2 * np.exp(-H**2)
    else:
        raise JibberishWarning('You just entered a jibberish covariance model')
    
    # RYY = np.exp(-abs(H)) * sigma2
    # RYY = np.exp(-H**2) * sigma2
    # RYY =(1-1.5*H+0.5*H**3)*sigma2
    # RYY[H>1]=0

    # ============== END COVARIANCE BLOCK =====================================
    
    # ============== BEGIN POWER-SPECTRUM BLOCK ===============================
    # Fourier Transform (Origin Shifted to Node (0,0))
    # Yields Power Spectrum of the field
    SYY=np.fft.fftn(np.fft.fftshift(RYY))/ntot;
    # Remove Imaginary Artifacts
    SYY=np.abs(SYY)
    SYY[0,0] =0;
    # ============== END POWER-SPECTRUM BLOCK =================================
       
    # ============== BEGIN FIELD GENERATION BLOCK =============================
    # Generate the field
    # nxhelp is nx with the first two entries switched
    if dimen > 1:
        nxhelp = np.array([nx[1], nx[0]])+1
    else:
        nxhelp = np.array([1,nx[0]]).T;

    # Generate the real field according to Dietrich and Newsam (1993)
    ran = np.multiply(np.sqrt(SYY),
                      (np.random.randn(*nxhelp) + 1j * np.random.randn(*nxhelp)))
    
    # Backtransformation into the physical coordinates
    ran = np.real(np.fft.ifftn(ran * ntot)) + mu

    
    
    # ran = np.multiply(np.sqrt(SYY), np.squeeze(
    #         np.array([np.random.randn(nxhelp[0], nxhelp[1]) + 
    #                   1j*np.random.randn(nxhelp[0], nxhelp[1])] 
    #                  ,dtype = 'complex_'))
    #         )
    # # Backtransformation into the physical coordinates
    # ran = np.real(np.fft.ifftn(ran*ntot))+mu;
    # ============== END FIELD GENERATION BLOCK ===============================
    
    return X, Y, ran







