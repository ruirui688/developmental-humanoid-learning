import json
from pathlib import Path
report=json.loads(Path('external/local_integration_20261011_development_audit.json').read_text(encoding='utf-8'))
seeds=report['archive']['seeds']
kinds=('frozen_euler_mpc','learned_euler_mpc','frozen_trapezoid_mpc','learned_trapezoid_mpc')
for trajectory in ('prediction',*kinds):
    print('TRAJECTORY',trajectory)
    for hi,h in enumerate((1,5,15,50)):
        means={name:tuple(sum(s['evaluations'][trajectory]['free_rollouts'][hi]['predictors'][name][key] for s in seeds)/3 for key in ('terminal_position_rmse_rad','terminal_velocity_rmse_rad_s')) for name in (*kinds,'velocity_persistence')}
        if trajectory=='prediction':print(h,{name:[round(x,12) for x in values] for name,values in means.items()})
        else:
            match=means[trajectory]
            print(h,'own_q_v',[round(x,12) for x in match],'learned_pair_q_v', [round(x,12) for x in means['learned_euler_mpc']],[round(x,12) for x in means['learned_trapezoid_mpc']], 'trap_pct_vs_euler',[(means['learned_trapezoid_mpc'][i]/means['learned_euler_mpc'][i]-1)*100 for i in (0,1)])
print('TRACKING_DETAIL')
for s in seeds:
    ev=s['evaluations']
    print(s['seed'], {kind: ev[kind]['tracking_rmse_rad'] for kind in kinds}, 'learned_trap_percent',(ev['learned_trapezoid_mpc']['tracking_rmse_rad']/ev['learned_euler_mpc']['tracking_rmse_rad']-1)*100)
print('FACTOR_MEANS')
for key in ('endpoint_euler','trapezoid'):
    print('learned_minus_nominal',key,sum(s['tracking_factorial_effects']['learned_minus_nominal'][key] for s in seeds)/3)
for key in ('nominal','learned'):
    print('trapezoid_minus_endpoint',key,sum(s['tracking_factorial_effects']['trapezoid_minus_endpoint'][key] for s in seeds)/3)
print('interaction_mean',sum(s['tracking_factorial_effects']['difference_of_differences'] for s in seeds)/3)
for kind in kinds:
    print('MODEL_CONTRIB',kind, 'riskguardsoftmax',max(s['evaluations'][kind]['control_risk']['soft_limit_excursion_peak_rad'] for s in seeds), 'fallbacks',sum(s['evaluations'][kind]['planner_fallbacks'] for s in seeds))
