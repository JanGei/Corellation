from joblib import Parallel, delayed
import numpy as np
import os
import time
    
class Ensemble:
    
    def __init__(self, members: list, pilotp_flag, nprocs: int, obs_cid: list, mask, ellipses = [], ellipses_par = [], pp_cid = [], pp_xy = [], pp_k = []):
        self.members    = members
        self.nprocs     = nprocs
        self.n_mem      = len(self.members)
        self.obs_cid    = [int(i) for i in obs_cid]
        self.ny         = len(obs_cid)
        self.h_mask     = mask.astype(bool)
        self.ole        = {'assimilation': [], 'prediction': []}
        self.ole_nsq    = {'assimilation': [], 'prediction': []}
        self.te1        = {'assimilation': [], 'prediction': []}
        self.te1_nsq    = {'assimilation': [], 'prediction': []}
        self.te2        = {'assimilation': [], 'prediction': []}
        self.te2_nsq    = {'assimilation': [], 'prediction': []}
        self.obs        = []
        self.pilotp_flag= pilotp_flag
        self.meanlogk   = []
        self.meank   = []
        if pilotp_flag:
            self.ellipses   = ellipses
            self.ellipses_par = ellipses_par
            self.pp_cid     = pp_cid
            self.pp_xy      = pp_xy
            self.mean_cov   = np.mean(ellipses, axis = 0)
            self.var_cov    = np.var(ellipses, axis = 0)
            self.mean_cov_par   = np.mean(ellipses_par, axis = 0)
            self.var_cov_par    = np.var(ellipses_par, axis = 0)
            self.meanlogppk = []
            self.varlogppk = []
            self.meanppk = []
            self.varppk = []
            self.pp_k_ini = pp_k
        
        
    def set_field(self, field, pkg_name: list):
        Parallel(n_jobs=self.nprocs, backend="threading")(delayed(self.members[idx].set_field)(
            [field[idx]],
            pkg_name) 
            for idx in range(self.n_mem)
            )
        
    def propagate(self):
        Parallel(n_jobs=self.nprocs, backend="threading")(delayed(self.members[idx].simulation)(
            ) 
            for idx in range(self.n_mem)
            )
        
    def update_initial_heads(self):
        Parallel(n_jobs=self.nprocs, backend="threading")(delayed(self.members[idx].update_ic)(
            ) 
            for idx in range(self.n_mem)
            )
        
    def get_damp(self, X, pars):
        val = pars['damp']
        damp = np.zeros((X[:,0].size)) + val[0]
        if 'cov_data' in pars['EnKF_p']:
            cl = len(np.unique(self.members[0].ellips_mat))
            damp[0], damp[2] = val[1][0], val[1][0]
            damp[1] = val[1][1]
            if 'npf' in pars['EnKF_p']:
                damp[cl:cl+len(self.pp_cid)] = val[2]
        else:
            if self.pilotp_flag:
                damp[:len(self.pp_cid)] = val[1]
            else:
                damp[:len(self.members[0].npf.k.array.squeeze())] = val[1]
            
        return damp
        
    def write_simulations(self):
        Parallel(n_jobs=self.nprocs,
                 backend="threading")(
                     delayed(self.members[idx].write_sim)()
                     for idx in range(self.n_mem)
                     )
        
    def apply_X(self, X, params):
        
        result = Parallel(n_jobs=self.nprocs, backend="threading")(delayed(self.members[idx].apply_x)(
            np.squeeze(X[:,idx]),
            self.h_mask,
            self.pp_xy,
            self.pp_cid,
            self.mean_cov_par,
            self.var_cov_par
            ) 
            for idx in range(self.n_mem)
            )
        
        cl = 3
        if 'cov_data' in params:
            # Only register ellipses that perfromed a successfull update
            self.ellipses = np.array([data[0] for data in result if data[2]])
            self.ellipses_par = [data[1] for data in result if data[2]]
            # self.mean_cov = np.mean(self.ellipses, axis = 0)
            self.var_cov = np.var(self.ellipses, axis = 0)
            self.mean_cov_par = np.mean(np.array(self.ellipses_par), axis = 0)
            self.var_cov_par = np.var(np.array(self.ellipses_par), axis = 0)
            if 'npf' in params:
                self.meanlogppk = np.mean(X[cl:len(self.pp_cid)+cl,:], axis = 1)
                self.varlogppk = np.var(X[cl:len(self.pp_cid)+cl,:], axis = 1)
                self.meanppk = np.mean(np.exp(X[cl:len(self.pp_cid)+cl,:]), axis = 1)
                self.varppk = np.var(np.exp(X[cl:len(self.pp_cid)+cl,:]), axis = 1)
        else:
            if self.pilotp_flag:
                self.meanlogppk = np.mean(X[:len(self.pp_cid),:], axis = 1)
                self.varlogppk = np.var(X[:len(self.pp_cid),:], axis = 1)
                self.meanppk = np.mean(np.exp(X[:len(self.pp_cid),:]), axis = 1)
                self.varppk = np.var(np.exp(X[:len(self.pp_cid),:]), axis = 1)
                    
    def get_Kalman_X_Y(self):   

        result = Parallel(n_jobs=self.nprocs, backend="threading")(delayed(self.members[idx].Kalman_vec)(
            self.h_mask,
            self.obs_cid,
            self.pp_cid 
            ) 
            for idx in range(self.n_mem)
            )
        
        xs = []
        ysims = []
        for tup in result:
            xs.append(tup[0])
            ysims.append(tup[1])
        
        X = np.vstack(xs).T
        Ysim = np.vstack(ysims).T
        return X, Ysim, np.mean(Ysim, axis = 1)
    
    def update_transient_data(self, rch_data, wel_data, riv_data):

        spds = self.members[0].get_field(['rch', 'wel', 'riv'])
        rch_spd = spds['rch']
        wel_spd = spds['wel']
        riv_spd = spds['riv']
        rivhl = np.ones(np.shape(riv_spd[0]['cellid']))
        rch_spd[0]['recharge'] = rch_data
        riv_spd[0]['stage'] = rivhl * riv_data
        wel_spd[0]['q'] = wel_data

        
        # this is the part that takes the most time 
        Parallel(n_jobs=self.nprocs)(delayed(self.members[idx].set_field)(
            [rch_spd, wel_spd, riv_spd],
            ['rch', 'wel', 'riv']
            ) 
            for idx in range(self.n_mem)
            )

    
    def model_error(self,  true_h, mean_h, var_h, period):
        
        mean_h = np.squeeze(mean_h)
        var_h = np.squeeze(var_h)
        true_h = np.squeeze(true_h)
        
        # analogous for ole
        mean_obs = mean_h[self.obs_cid]
        true_obs = true_h[self.obs_cid]
        self.obs = [true_obs, mean_obs]
        
        self.ole_nsq[period].append(np.sum(np.square(true_obs - mean_obs)/0.01**2)/mean_obs.size)
        
        # ole for the model up until the current time step
        self.ole[period].append(np.sqrt(np.sum(self.ole_nsq[period])/len(self.ole_nsq[period])))
        
        # calculating nrmse without root for later summation
        true_h = true_h[~self.h_mask]
        mean_h = mean_h[~self.h_mask]
        var_h = var_h[~self.h_mask]
        var_te2 = (true_h + mean_h)/2
        
        self.te1_nsq[period].append(np.sum(np.square(true_h - mean_h)/var_h))
        self.te2_nsq[period].append(np.sum(np.square(true_h - mean_h)/var_te2**2))
        
        # nrmse for the model up until the current time step
        self.te1[period].append(np.sqrt(np.sum(self.te1_nsq[period])/len(self.te1_nsq[period])/mean_h.size))
        self.te2[period].append(np.sqrt(np.sum(self.te2_nsq[period])/len(self.te2_nsq[period])/mean_h.size))
    
    def get_member_fields(self, params):
        
        data = Parallel(n_jobs=self.nprocs, backend="threading")(delayed(self.members[idx].get_field)(
            params
            ) 
            for idx in range(self.n_mem)
            )
        
        return data
        

    def get_mean_var(self, h = 'h'):
        h_fields = self.get_member_fields([h])
        
        h_f = np.array([np.squeeze(field[h]) for field in h_fields]).T
        
        return np.mean(h_f, axis = 1), np.var(h_f, axis = 1)
    
    def record_state(self, pars: dict, params: list, true_h, period: str, year):
        
        mean_h, var_h = self.get_mean_var(h = 'ic')
        k_fields = self.get_member_fields(['npf'])
        k_fields = np.array([field['npf'] for field in k_fields]).squeeze()
        self.meanlogk = np.mean(np.log(k_fields), axis = 0)
        self.meank = np.mean(k_fields, axis = 0)
        
        direc = pars['resdir']
        
        f = open(os.path.join(direc,  'h_mean.dat'),'a')
        g = open(os.path.join(direc,  'h_var.dat'),'a')
        h = open(os.path.join(direc,  'true_h.dat'),'a')
        for i in range(len(mean_h)):
            f.write("{:.5f} ".format(mean_h[i]))
            g.write("{:.5f} ".format(var_h[i]))
            h.write("{:.5f} ".format(true_h[i]))
        f.write('\n')
        g.write('\n')
        h.write('\n')
        f.close()
        g.close()
        h.close()
        
        f = open(os.path.join(direc,  'errors_'+period+str(year)+'.dat'),'a')
        f.write("{:.4f} ".format(self.ole[period][-1]))
        f.write("{:.4f} ".format(self.te1[period][-1]))
        f.write("{:.4f} ".format(self.te2[period][-1]))
        f.write('\n')
        f.close()
        
        f = open(os.path.join(direc,  'obs_true.dat'),'a')
        g = open(os.path.join(direc,  'obs_mean.dat'),'a')
        for i in range(len(self.obs[0])):
            f.write("{:.5f} ".format(self.obs[0][i]))
            g.write("{:.5f} ".format(self.obs[1][i]))
        f.write('\n')
        g.write('\n')
        f.close()
        g.close()
        
        
        
        # also store covariance data for all models
        if 'cov_data' in params:
            cov_data = self.get_member_fields(['cov_data'])
            
            mat = np.array([[self.mean_cov_par[0], self.mean_cov_par[1]],
                            [self.mean_cov_par[1], self.mean_cov_par[2]]])
            res = pars['mat2cv'](mat)
                
            f = open(os.path.join(direc, 'covariance_data.dat'),'a')
            f.write("{:.10f} ".format(res[0]))
            f.write("{:.10f} ".format(res[1]))
            f.write("{:.10f} ".format(res[2]))
            f.write('\n')
            f.close()
            
            f = open(os.path.join(direc, 'cov_variance.dat'),'a')
            f.write("{:.10f} ".format(self.var_cov[0]))
            f.write("{:.10f} ".format(self.var_cov[1]))
            f.write("{:.10f} ".format(self.var_cov[2]))
            f.write('\n')
            f.close()
            
            f = open(os.path.join(direc, 'covariance_data_par.dat'),'a')
            f.write("{:.10f} ".format(self.mean_cov_par[0]))
            f.write("{:.10f} ".format(self.mean_cov_par[1]))
            f.write("{:.10f} ".format(self.mean_cov_par[2]))
            f.write('\n')
            f.close()
            
            f = open(os.path.join(direc, 'cov_variance_par.dat'),'a')
            f.write("{:.10f} ".format(self.var_cov_par[0]))
            f.write("{:.10f} ".format(self.var_cov_par[1]))
            f.write("{:.10f} ".format(self.var_cov_par[2]))
            f.write('\n')
            f.close()
            
            for i in range(self.n_mem):
                f = open(os.path.join(direc, f'covariance_model_{i}.dat'), 'a')
                for j in range(len(cov_data[i]['cov_data'])):
                    f.write("{:.10f} ".format(cov_data[i]['cov_data'][j]))
                f.write('\n')
                f.close()

        if 'npf' in params:
            if self.pilotp_flag:
                f = open(os.path.join(direc,  'meanlogppk.dat'),'a')
                g = open(os.path.join(direc,  'varlogppk.dat'),'a')
                for i in range(len(self.meanlogppk)):
                    f.write("{:.8f} ".format(self.meanlogppk[i]))
                    g.write("{:.8f} ".format(self.varlogppk[i]))
                f.write('\n')
                g.write('\n')
                f.close()
                g.close()
                
                f = open(os.path.join(direc,  'meanppk.dat'),'a')
                g = open(os.path.join(direc,  'varppk.dat'),'a')
                for i in range(len(self.meanppk)):
                    f.write("{:.8f} ".format(self.meanppk[i]))
                    g.write("{:.8f} ".format(self.varppk[i]))
                f.write('\n')
                g.write('\n')
                f.close()
                g.close()
            
            f = open(os.path.join(direc,  'meanlogk.dat'),'a')
            for i in range(len(self.meanlogk)):
                f.write("{:.8f} ".format(self.meanlogk[i]))
            f.write('\n')
            f.close()
            
            f = open(os.path.join(direc,  'meank.dat'),'a')
            for i in range(len(self.meank)):
                f.write("{:.8f} ".format(self.meank[i]))
            f.write('\n')
            f.close()
        
    def remove_current_files(self, pars):
        
        file_paths = [os.path.join(pars['resdir'], 'errors_assimilation.dat'),
                      os.path.join(pars['resdir'], 'errors_prediction.dat'),
                      os.path.join(pars['resdir'], 'errors_assimilation2.dat'),
                      os.path.join(pars['resdir'], 'errors_prediction2.dat'),
                      os.path.join(pars['resdir'], 'covariance_data.dat'),
                      os.path.join(pars['resdir'], 'cov_variance.dat'),
                      os.path.join(pars['resdir'], 'covariance_data_par.dat'),
                      os.path.join(pars['resdir'], 'cov_variance_par.dat'),
                      os.path.join(pars['resdir'], 'meanppk.dat'),
                      os.path.join(pars['resdir'], 'varppk.dat'),
                      os.path.join(pars['resdir'], 'meanlogppk.dat'),
                      os.path.join(pars['resdir'], 'varlogppk.dat'),
                      os.path.join(pars['resdir'], 'obs_true.dat'),
                      os.path.join(pars['resdir'], 'meank.dat'),
                      os.path.join(pars['resdir'], 'meanlogk.dat'),
                      os.path.join(pars['resdir'], 'k_mean.dat'),
                      os.path.join(pars['resdir'], 'h_mean.dat'),
                      os.path.join(pars['resdir'], 'h_var.dat'),
                      os.path.join(pars['resdir'], 'obs_mean.dat'),
                      os.path.join(pars['resdir'], 'true_h.dat'),
                      ]
        
        for file_path in file_paths:
            if os.path.exists(file_path):
                os.remove(file_path)
        
        for filename in os.listdir(pars['resdir']):
            # Check if the surname is in the filename
            if 'covariance_model_' in filename:
                # Construct the full file path
                file_path = os.path.join(pars['resdir'], filename)
                # Remove the file
                os.remove(file_path)

        


    def reset_errors(self):
        self.ole        = {'assimilation': [], 'prediction': []}
        self.ole_nsq    = {'assimilation': [], 'prediction': []}
        self.te1        = {'assimilation': [], 'prediction': []}
        self.te1_nsq    = {'assimilation': [], 'prediction': []}
        self.te2        = {'assimilation': [], 'prediction': []}
        self.te2_nsq    = {'assimilation': [], 'prediction': []}
        
        
        
        
        
        
        
        
        
        