from dependencies.model_params import get
from dependencies.copy import create_Ensemble, create_shadow_Ensemble
# from dependencies.convert_transient import convert_to_transient
from dependencies.create_pilot_points import create_pilot_points_even, create_pilot_points
from dependencies.load_template_model import load_template_model
from dependencies.create_k_fields import create_k_fields
from dependencies.write_file import write_file
from dependencies.get_transient_data import get_transient_data
from dependencies.intersect_with_grid import intersect_with_grid
from dependencies.generate_mask import chd_mask
from dependencies.plotting.ellipses import ellipses
from dependencies.implicit_localisation import implicit_localisation
from dependencies.plotting.compare_mean import compare_mean_true 
from dependencies.plotting.compare_mean_h import compare_mean_true_head
from dependencies.shoutout_difference import shout_dif
from objects.Ensemble import Ensemble
from objects.MFModel import MFModel
from objects.Virtual_Reality import Virtual_Reality
from objects.EnsembleKalmanFilter import EnsembleKalmanFilter
from Virtual_Reality.ReferenceModel import create_reference_model
import time
import numpy as np
from joblib import Parallel, delayed

import warnings

# Define a filter function to suppress specific warnings
def joblib_warning_filter(message, category, filename, lineno, file=None, line=None):
    if "joblib" in str(filename):
        return None  # Suppress the warning
    else:
        return message, category, filename, lineno, None, None


if __name__ == '__main__':

    # Register the filter function with the warnings module
    warnings.showwarning = joblib_warning_filter
    
    pars        = get()
    n_mem       = pars['n_mem']
    nprocs      = pars['nprocs']
    
    if pars['up_tem']:
        create_reference_model(pars)
    
    
    print(f'Joblib initiated with {nprocs} processors')
    print(f'The template model is located in {pars["tm_ws"]}')
    #%% loading necessary data
    start_time = time.time()
    
    # copy template model to ensemble folder
    model_dir = create_Ensemble(pars)
    model_dir_iso = create_Ensemble(pars, iso = True)
    sim, gwf = load_template_model(pars)
    mask_chd = chd_mask(gwf)
    
    obs_cid = intersect_with_grid(gwf, pars['obsxy'])
    
    VR_Model = Virtual_Reality(pars, obs_cid)
    
    k_fields = []
    k_fields_iso = []
    cor_ellips = []
    l_angs = []
    lx_iso = []
    pp_k_ini = []
    pp_k_ini_iso = []
    
    
    if pars['pilotp']:
        if pars['ppeven']:
            pp_cid, pp_xy = create_pilot_points_even(gwf, pars)
        else:
            pp_cid, pp_xy = create_pilot_points(gwf, pars)
            
        # create_k_fields
        result = Parallel(n_jobs=nprocs, backend = pars['backnd'])(delayed(create_k_fields)(
            gwf,
            pars, 
            VR_Model.npf.k.array,
            pp_xy,
            pp_cid,
            conditional = pars['condfl']
            )
            for idx in range(n_mem)
            )
        # sorting the results
        for tup in result:
            field, ellips, l_ang, pilotpoints, field_iso, pp_k_iso, lx_iso = tup
            k_fields.append(field)
            k_fields_iso.append(field_iso)
            cor_ellips.append(ellips)
            l_angs.append(l_ang)
            pp_k_ini.append(pilotpoints[1])
            pp_k_ini_iso.append(pp_k_ini_iso)
    
    # save original fields from dependencies.plotting.plot_k_fields import plot_k_fields
    # if pars['setup'] == 'binnac':
    #     np.save(os.path.join(pars['resdir'] ,'k_ensemble_ini.npy'), k_fields)
    print(f'The model has {len(obs_cid)} observation points')
    if pars['pilotp']:
        print(f'The model has {len(pp_cid)} pilot points points')
    if pars['printf']: print(f'Loading of data and creating k_fields took {(time.time() - start_time):.2f} seconds')
    
    #%% generate model instances  
    start_time = time.time()
    models = Parallel(n_jobs=nprocs, backend="threading")(delayed(MFModel)(
                        model_dir[idx],
                        pars,
                        obs_cid,
                        [pp_xy, pp_cid],
                        l_angs[idx],
                        cor_ellips[idx],
                        ) 
                        for idx in range(n_mem)
                        )
    
    models_iso = Parallel(n_jobs=nprocs, backend="threading")(delayed(MFModel)(
        model_dir_iso[idx],
        pars,
        obs_cid,
        [pp_xy, pp_cid],
        lx_iso,
        iso = True
        ) 
        for idx in range(n_mem)
        )
    
    if pars['printf']: print(f'{n_mem} models are initiated in {(time.time() - start_time):.2f} seconds')
    
    #%% add the models to the ensemble
    start_time = time.time()
    
    MF_Ensemble     = Ensemble(models,
                               pars,
                               obs_cid,
                               nprocs,
                               mask_chd,
                               np.squeeze(VR_Model.npf.k.array),
                               np.array(l_angs),
                               np.array(cor_ellips),
                               pp_cid,
                               pp_xy,
                               pp_k_ini)
    MF_Ensemble.remove_current_files(pars)
    
    MF_Ensemble_iso = Ensemble(models_iso,
                               pars,
                               obs_cid,
                               nprocs,
                               mask_chd,
                               np.squeeze(VR_Model.npf.k.array),
                               pp_cid = pp_cid,
                               pp_xy = pp_xy,
                               pp_k = pp_k_ini_iso,
                               iso = True)
    MF_Ensemble.remove_current_files(pars)
    MF_Ensemble_iso.remove_current_files(pars)
    write_file(pars,[pp_cid, pp_xy], ["pp_cid","pp_xy"], 0, intf = True)
    # set their respective k-fields
    MF_Ensemble.set_field(k_fields, ['npf'])
    MF_Ensemble_iso.set_field(k_fields_iso, ['npf'])
    # MF_Ensemble.set_field([VR_Model.npf.k.array for i in range(len(models))], ['npf'])
    
    m = np.mean(cor_ellips, axis = 0)
    mat = np.array([[m[0], m[1]],[m[1], m[2]]])
    ellipses(
        MF_Ensemble.ellipses,
        pars['mat2cv'](mat),
        pars
        )
    
    if pars['printf']: print(f'Ensemble is initiated and respective k-fields are set in {(time.time() - start_time):.2f} seconds')
    
    start_time = time.time()
    MF_Ensemble.update_initial_conditions()
    MF_Ensemble_iso.update_initial_conditions()
    
    if pars['printf']: print(f'Ensemble now with steady state initial conditions in {(time.time() - start_time):.2f} seconds')
    #%% Setup EnKF for Ensemble and perform spinup 
    X, Ysim = MF_Ensemble.get_Kalman_X_Y()
    X_iso, Ysim_iso = MF_Ensemble_iso.get_Kalman_X_Y()
    
    damp = MF_Ensemble.get_damp(X)
    damp_iso = MF_Ensemble_iso.get_damp(X_iso)
    
    local_matrix = implicit_localisation(pars['obsxy'], gwf.modelgrid, mask_chd, pars['EnKF_p'], pp_xy = pp_xy)
    local_matrix_iso = implicit_localisation(pars['obsxy'], gwf.modelgrid, mask_chd, pars['EnKF_p'], pp_xy = pp_xy, iso = True)
    
    EnKF = EnsembleKalmanFilter(X, Ysim, damp = damp, eps = pars['eps'], localisation=local_matrix)
    EnKF_iso = EnsembleKalmanFilter(X_iso, Ysim_iso, damp = damp_iso, eps = pars['eps'], localisation=local_matrix_iso)
    
    true_obs = np.zeros((pars['nsteps'],len(obs_cid)))
    
    if pars['spinup']:
        for t_step in range(pars['nsteps']):
            if t_step%4 == 0:
                data, packages = get_transient_data(pars, t_step)
                VR_Model.update_transient_data(data, packages)
                MF_Ensemble.update_transient_data(packages)
                MF_Ensemble_iso.update_transient_data(packages)
            VR_Model.simulation()
            true_h = VR_Model.update_ic()
            MF_Ensemble.propagate()  
            MF_Ensemble.update_initial_heads()
            MF_Ensemble_iso.propagate()  
            MF_Ensemble_iso.update_initial_heads()
            if pars['printf']: 
                print('--------')
                print(f'time step {t_step}')
                true_obs[t_step,:] = np.squeeze(VR_Model.get_observations())
                X, Ysim = MF_Ensemble.get_Kalman_X_Y()
                shout_dif(true_obs[t_step,:], np.mean(Ysim, axis = 1))
                
    #%% Define Shadow Ensemble and assimmilation scheme
    # if pars['shadow']:
    #     shadow_model_dir = create_shadow_Ensemble(pars)
    #     shadow_models = Parallel(n_jobs=nprocs, backend="threading")(delayed(MFModel)(
    #                             shadow_model_dir[idx],
    #                             pars,
    #                             obs_cid,
    #                             [pp_xy, pp_cid],
    #                             l_angs[idx],
    #                             cor_ellips[idx],
    #                             ) 
    #                             for idx in range(n_mem)
    #                             )
    #     MF_shadowEnsemble = Ensemble(shadow_models,
    #                                pars,
    #                                obs_cid,
    #                                nprocs,
    #                                mask_chd,
    #                                np.squeeze(VR_Model.npf.k.array),
    #                                np.array(l_angs),
    #                                np.array(cor_ellips),
    #                                pp_cid,
    #                                pp_xy,
    #                                pp_k_ini,
    #                                shadow = True)
    #     # X_shadow, Ysim_shadow = MF_shadowEnsemble.get_Kalman_X_Y()
    #     # damp = MF_shadowEnsemble.get_damp(X)
    #     # local_matrix = implicit_localisation(pars['obsxy'], gwf.modelgrid, mask_chd, pars['EnKF_p'], pp_xy = pp_xy)
    #     # EnKF = EnsembleKalmanFilter(X, Ysim, damp = damp, eps = pars['eps'], localisation=local_matrix)
    #     # true_obs = np.zeros((pars['nsteps'],len(obs_cid)))
    
    
    for t_step in range(pars['nsteps']):
        
        period, Assimilate = pars['period'](t_step, pars)  
        if t_step/4 == pars['asim_d'][1]:
            MF_Ensemble.reset_errors()
            MF_Ensemble_iso.reset_errors()
        elif pars['val1st'] and t_step/4 == pars['asim_d'][0]+pars['valday']:
            damp = MF_Ensemble.get_damp(X, switch = True)
            EnKF.update_damp(damp)
            
        print('--------')
        print(f'time step {t_step}')
        start_time_ts = time.time()
        if t_step%4 == 0:
            data, packages = get_transient_data(pars, t_step)
            
            VR_Model.update_transient_data(data, packages)
            MF_Ensemble.update_transient_data(packages)
            MF_Ensemble_iso.update_transient_data(packages)
            # if pars['shadow']:
            #     MF_shadowEnsemble.update_transient_data(packages)

            if pars['printf']: print(f'transient data loaded and applied in {(time.time() - start_time_ts):.2f} seconds')
        
        if pars['printf']: print('---')
        start_time = time.time()
        VR_Model.simulation()
        MF_Ensemble.propagate()
        MF_Ensemble_iso.propagate()
        # if pars['shadow']:
        #     MF_shadowEnsemble.propagate()
            
        if pars['printf']: print(f'Ensemble propagated in {(time.time() - start_time):.2f} seconds')

        if Assimilate:
            # print('---')
            # if pars['shadow']:
            #     MF_shadowEnsemble.update_initial_heads()
            start_time = time.time()
            X, Ysim = MF_Ensemble.get_Kalman_X_Y()
            X_iso, Ysim_iso = MF_Ensemble_iso.get_Kalman_X_Y()
            EnKF.update_X_Y(X, Ysim)
            EnKF_iso.update_X_Y(X_iso, Ysim_iso)
            EnKF.analysis()
            EnKF_iso.analysis()
            
            true_obs[t_step,:] = np.squeeze(VR_Model.get_observations())
            if pars['printf']: shout_dif(true_obs[t_step,:], np.mean(Ysim, axis = 1))
            EnKF.Kalman_update(true_obs[t_step,:].T, t_step)
            EnKF_iso.Kalman_update(true_obs[t_step,:].T, t_step)

            if pars['printf']: print(f'Ensemble Kalman Filter performed in  {(time.time() - start_time):.2f} seconds')

            start_time = time.time()
            MF_Ensemble.apply_X(EnKF.X)
            MF_Ensemble_iso.apply_X(EnKF_iso.X)
            
            if pars['printf']: interim = [int(i+len(damp) -5000) for i in obs_cid]
            if pars['printf']: shout_dif(true_obs[t_step,:], np.mean(EnKF.X, axis = 1)[interim])
            if pars['printf']: print(f'Application of results plus kriging took {(time.time() - start_time):.2f} seconds')
        else:
            # Very important: update initial conditions if youre not assimilating
            MF_Ensemble.update_initial_heads()
            MF_Ensemble_iso.update_initial_heads()
            # if pars['shadow']:
            #     MF_shadowEnsemble.update_initial_heads()
        
        # Update the intial conditiopns of the "true model"
        true_h = VR_Model.update_ic()
        
        MF_Ensemble.log(t_step)
        # if pars['shadow']:
        #     MF_shadowEnsemble.log(t_step)
        
        start_time = time.time()
        if period == "assimilation" or period == "prediction":
            if t_step%4 == 0:
                
                
                mean_h, var_h = MF_Ensemble.model_error(true_h, period)
                MF_Ensemble.record_state(pars, np.squeeze(true_h), period, t_step)
                
                mean_h_iso, var_h_iso = MF_Ensemble_iso.model_error(true_h, period)
                MF_Ensemble_iso.record_state(pars, np.squeeze(true_h), period, t_step)
                
                # if pars['shadow']:
                #     mean_h, var_h = MF_shadowEnsemble.model_error(true_h, period)
                #     MF_shadowEnsemble.record_shadow_state(pars, np.squeeze(true_h), period, t_step)
                
                # visualize covariance structures
                if pars['setup'] == 'office' and Assimilate and t_step%12 == 0:
                    if 'cov_data' in MF_Ensemble.params:
                        m = MF_Ensemble.mean_cov_par
                        mat = np.array([[m[0], m[1]],[m[1], m[2]]])
                        ellipses(
                            MF_Ensemble.ellipses,
                            pars['mat2cv'](mat),
                            pars
                            )
                    if t_step%40 == 0:
                        compare_mean_true(gwf, [np.squeeze(VR_Model.npf.k.array), MF_Ensemble.meanlogk, MF_Ensemble.varlogk], pp_xy[pars['f_m_id']])
                        compare_mean_true_head(gwf, [np.squeeze(true_h), np.squeeze(mean_h), np.squeeze(var_h)], pp_xy[pars['f_m_id']]) 
                
                if pars['printf']: print(f'Plotting and recording took {(time.time() - start_time):.2f} seconds')
                if pars['printf']: print(f'Entire Step took {(time.time() - start_time_ts):.2f} seconds')
    