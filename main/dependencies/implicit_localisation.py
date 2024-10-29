import numpy as np
from scipy.spatial import distance


def implicit_localisation(obs_xy, modelgrid, mask, parameters, pp_xy = []):
    x,y,_ = modelgrid.xyzcellcenters
    cxy = np.array([x,y]).T 
    cxy = cxy[~np.asarray(mask, dtype = bool)]
    
    if 'npf' in parameters:
       cxy = np.vstack([pp_xy, cxy])
      
    dist_matrix = distance.cdist(obs_xy, cxy, metric='euclidean')
    
    distance_weighted_matrix = steep_norm(dist_matrix, threshold = 2000, steepness= 7)
    
    if 'cov_data' in parameters:
        distance_weighted_matrix = np.hstack([np.ones((np.shape(distance_weighted_matrix)[0], 3)), distance_weighted_matrix])
    
    return distance_weighted_matrix


def steep_norm(x, threshold=1500, steepness=10, cutoff = 2500):
    """
    Normalize x between 0 and 1 with a steep decline, setting all values above the threshold to 0.
    
    Parameters:
    x : numpy array of values to be normalized
    threshold : float, value above which everything will be set to 0 (default: 1500)
    steepness : float, controls the steepness of the decline (default: 10)
    
    Returns:
    normalized : numpy array with values normalized between 0 and 1 with a steep decline
    """
    # Set all values greater than the threshold to 0
    # x_clipped = np.where(x > threshold, threshold, x)
    x_clipped = x
    
    # Normalize remaining values between 0 and 1 using min-max scaling
    if np.max(x_clipped) != np.min(x_clipped):  # Avoid division by zero
        # Normalization to make the values smaller compared to the threshold
        x_norm = (x_clipped - np.min(x_clipped)) / (threshold - np.min(x_clipped))
    else:
        x_norm = x_clipped  
    
    # Apply steep sigmoid-like function (to ensure steepness around the normalized threshold)
    decline = 1 / (1 + np.exp(steepness * (x_norm - 0.7)))  # Adjust threshold to 0.5 in normalized range
    decline = np.where(x > cutoff, 0, decline)
    return decline