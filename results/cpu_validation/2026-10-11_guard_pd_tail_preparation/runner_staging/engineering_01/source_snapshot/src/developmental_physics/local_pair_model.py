"""Draft native-only two-output RLS and constant-vector finite-grid MPC.

This mathematical core reads only encoder q/v and requested u. It has no
simulation dependency, task teacher, future-state input or physical query.
No C4 protocol or scientific acceptance gate is implied by this draft.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Mapping

import numpy as np

from .local_model import (
    FORGETTING_FACTOR, HINGE_THRESHOLD_NM, INITIAL_COVARIANCE,
    MPCConfig, _digest, _scalar,
)


def _pair(name, value):
    try:
        items = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain two finite native scalars") from exc
    if items.shape != (2,):
        raise ValueError(f"{name} must contain two finite native scalars")
    return tuple(_scalar(f"{name}[{i}]", item) for i, item in enumerate(items))


class PairPredictionError(ValueError):
    """A rejected mathematical prediction with exact attempted-output costs."""
    def __init__(self, cause, attempts, successes, stage):
        super().__init__(str(cause))
        self.scalar_prediction_attempts = attempts
        self.scalar_prediction_successes = successes
        self.failure_stage = stage

    def to_dict(self):
        return {"type":type(self).__name__,"message":str(self),
                "scalar_prediction_attempts":self.scalar_prediction_attempts,
                "scalar_prediction_successes":self.scalar_prediction_successes,
                "failure_stage":self.failure_stage}


class PairUpdateError(ValueError):
    """A failed update retains proposals and the actual committed state."""
    def __init__(self, cause, *, proposed_outputs, snapshot, committed_scalar_updates=0):
        super().__init__(f"atomic pair update rejected: {cause}")
        self.proposed_outputs = proposed_outputs
        self.snapshot_after_attempt = snapshot
        self.committed_scalar_updates = committed_scalar_updates

    def to_dict(self):
        return {"type":type(self).__name__,"message":str(self),
                "committed_scalar_updates":self.committed_scalar_updates,"proposed_outputs":self.proposed_outputs,
                "snapshot_after_attempt":self.snapshot_after_attempt}


class SharedPairUpdateError(ValueError):
    """A later model failed; earlier committed model updates are retained."""
    def __init__(self, cause, *, failed_model, completed_records, snapshots, transition_id):
        super().__init__(f"shared transition update failed in {failed_model}: {cause}")
        self.failed_model = failed_model
        self.completed_records = completed_records
        self.snapshots_after_attempt = snapshots
        self.transition_id = transition_id
        attached = getattr(cause,"pair_update_accounting",None)
        self.failure_record = (attached if attached is not None else
            (cause.to_dict() if hasattr(cause,"to_dict") else {
                "type":type(cause).__name__,"message":str(cause)}))

    def to_dict(self):
        return {"type":type(self).__name__,"message":str(self),"failed_model":self.failed_model,
                "shared_transition_id":self.transition_id,
                "completed_model_records":self.completed_records,
                "snapshots_after_attempt":self.snapshots_after_attempt,
                "failure_record":self.failure_record}


@dataclass(frozen=True)
class _PairParameterState:
    """One published reference contains every mutable RLS quantity."""
    theta: np.ndarray
    covariance: np.ndarray
    vector_update_count: int


def _parameter_state(theta, covariance, vector_update_count):
    # The arrays are owned by this new state and never changed after publish.
    theta.setflags(write=False)
    covariance.setflags(write=False)
    return _PairParameterState(theta,covariance,vector_update_count)


class PairBodyModel:
    """Two next-velocity heads; both outputs commit atomically per model.

    A vector transition contributes two scalar labels. In a comparison, a
    successful diagonal update stays committed even if a subsequent coupled
    update fails; update_shared_models exposes that cross-model partial result.
    """
    def __init__(self, qref, *, structure, dt=.02, trainable=True):
        if structure not in ("diagonal_hinge5","coupled_hinge9"):
            raise ValueError("declared diagonal_hinge5 or coupled_hinge9 structure required")
        if type(trainable) is not bool:
            raise ValueError("trainable must be boolean")
        self._qref = _pair("qref",qref)
        self._dt = _scalar("dt",dt)
        if self._dt != .02:
            raise ValueError("draft pair model fixes the complete interval at 20 ms")
        self._structure = structure
        self._trainable = trainable
        size = 5 if structure == "diagonal_hinge5" else 9
        theta = np.zeros((2,size),dtype=np.float64)
        if size == 5:
            theta[:,0] = 1.
            theta[:,2] = .02
        else:
            for i in range(2):
                theta[i,i] = 1.
                theta[i,4+i] = .02
        self._initial_theta = theta.copy()
        covariance = np.repeat((INITIAL_COVARIANCE*np.eye(size))[None,:,:],2,axis=0)
        self._state = _parameter_state(theta,covariance,0)

    @property
    def qref(self):
        return self._qref

    @property
    def dt(self):
        return self._dt

    @property
    def trainable(self):
        return self._trainable

    @property
    def structure(self):
        return self._structure

    @property
    def update_count(self):
        """Committed vector transitions, each containing two scalar updates."""
        return self._state.vector_update_count

    @property
    def scalar_update_count(self):
        return 2*self._state.vector_update_count

    @property
    def coefficients(self):
        return self._state.theta.copy()

    @property
    def covariance(self):
        return self._state.covariance.copy()

    def _features(self,q,v,u):
        positions,velocities,commands = (_pair(name,value) for name,value in (("q",q),("v",v),("u",u)))
        with np.errstate(over="ignore",invalid="ignore"):
            displacements = np.asarray(positions)-np.asarray(self.qref)
            hinges = np.sign(commands)*np.maximum(np.abs(commands)-HINGE_THRESHOLD_NM,0.)
            if self.structure == "diagonal_hinge5":
                features = np.asarray([[velocities[i],displacements[i],commands[i],hinges[i],1.] for i in range(2)],dtype=np.float64)
            else:
                row = np.asarray([*velocities,*displacements,*commands,*hinges,1.],dtype=np.float64)
                features = np.repeat(row[None,:],2,axis=0)
        if not np.isfinite(features).all():
            raise ValueError("native pair features must remain finite")
        return positions,features

    def _predict_output(self,index,features,state=None):
        state = self._state if state is None else state
        with np.errstate(over="ignore",invalid="ignore"):
            velocity = float(state.theta[index] @ features)
        if not np.isfinite(velocity):
            raise ValueError("pair velocity prediction overflowed")
        return velocity

    def predict(self,q,v,u):
        return self._predict_state(q,v,u,self._state)

    def _predict_state(self,q,v,u,state):
        attempts = successes = 0
        try:
            positions,features = self._features(q,v,u)
        except ValueError as exc:
            raise PairPredictionError(exc,0,0,"native_features") from exc
        velocities=[]
        for i in range(2):
            attempts+=1
            try:
                velocities.append(self._predict_output(i,features[i],state))
            except ValueError as exc:
                raise PairPredictionError(exc,attempts,successes,f"velocity_output_{i}") from exc
            except BaseException as exc:
                exc.pair_prediction_accounting={"scalar_prediction_attempts":attempts,
                    "scalar_prediction_successes":successes,"scalar_counts_complete":True,
                    "failure_stage":f"velocity_output_{i}"}
                raise
            successes+=1
        with np.errstate(over="ignore",invalid="ignore"):
            next_q = np.asarray(positions)+self.dt*np.asarray(velocities)
        if not np.isfinite(next_q).all():
            raise PairPredictionError(ValueError("pair position prediction overflowed"),attempts,successes,"endpoint_euler")
        return tuple(float(x) for x in next_q),tuple(velocities)

    def _parameter_record(self,state=None):
        state = self._state if state is None else state
        features = ([[f"v{i}",f"q{i}-qref{i}",f"u{i}",f"h(u{i})","1"] for i in range(2)]
                    if self.structure == "diagonal_hinge5" else
                    [["v0","v1","q0-qref0","q1-qref1","u0","u1","h(u0)","h(u1)","1"]]*2)
        return {"structure":self.structure,"qref_rad":list(self.qref),"dt_seconds":self.dt,
                "features_per_output":features,"coefficients":state.theta.tolist(),
                "covariance":state.covariance.tolist(),"initial_coefficients":self._initial_theta.tolist(),
                "initial_covariance_scale":INITIAL_COVARIANCE,"forgetting_factor":FORGETTING_FACTOR,
                "hinge_threshold_nm":HINGE_THRESHOLD_NM,"hinge_threshold_updates":0,
                "integration":"endpoint_euler","dtype":"float64"}

    def parameter_fingerprint(self):
        return _digest(self._parameter_record())

    def snapshot(self):
        return self._snapshot_state(self._state)

    def _snapshot_state(self,state):
        record = self._parameter_record(state)
        count = state.vector_update_count
        return {**record,"parameter_fingerprint":_digest(record),
                "trainable":self.trainable,"vector_update_count":count,
                "scalar_update_count":2*count,"output_update_counts":[count]*2,
                "update_commit":"single immutable state reference for both outputs, covariance and counts",
                "initial_prior":"generic velocity continuity and torque response; zero cross coefficients",
                "input_boundary":"current native q/v and already known requested u; no actual future torque or simulator state"}

    def clone_frozen(self):
        state = self._state
        clone = PairBodyModel(self.qref,structure=self.structure,dt=self.dt,trainable=False)
        clone._state = _parameter_state(state.theta.copy(),state.covariance.copy(),state.vector_update_count)
        return clone

    def _propose_update(self,index,features,label,predicted_v,state=None):
        state = self._state if state is None else state
        residual = label-predicted_v
        if not np.isfinite(residual):
            raise ValueError("RLS residual overflowed")
        try:
            with np.errstate(over="raise",invalid="raise",divide="raise"):
                projected = state.covariance[index] @ features
                denominator = FORGETTING_FACTOR+float(features @ projected)
                if not np.isfinite(denominator) or denominator <= 0:
                    raise ValueError("RLS denominator must be finite and positive")
                gain = projected/denominator
                theta = state.theta[index]+gain*residual
                covariance = (state.covariance[index]-np.outer(gain,projected))/FORGETTING_FACTOR
                covariance = .5*(covariance+covariance.T)
        except FloatingPointError as exc:
            raise ValueError("RLS proposal arithmetic overflowed") from exc
        if not np.isfinite(theta).all() or not np.isfinite(covariance).all():
            raise ValueError("RLS proposals must remain finite")
        return {"output_index":index,"features":features.tolist(),"observed_next_v_rad_s":label,
                "preupdate_error_rad_s":residual,"proposed_coefficients":theta.tolist(),
                "proposed_covariance":covariance.tolist(),"committed":False}

    def update(self,q,v,u,next_v,*,phase="identification",transition_id=None):
        if not self.trainable:
            raise RuntimeError("frozen pair evaluation model cannot update")
        if phase not in ("prefix","identification"):
            raise ValueError("phase must be prefix or identification")
        state = self._state
        positions,features = self._features(q,v,u)
        labels = _pair("next_v",next_v)
        predicted_q,predicted_v = self._predict_state(positions,v,u,state)
        before = _digest(self._parameter_record(state))
        proposals=[]
        try:
            next_state = state
            if phase != "prefix":
                for i in range(2):
                    proposals.append(self._propose_update(i,features[i],labels[i],predicted_v[i],state))
                # Allocate and validate both output states before one commit.
                theta = np.asarray([p["proposed_coefficients"] for p in proposals],dtype=np.float64)
                covariance = np.asarray([p["proposed_covariance"] for p in proposals],dtype=np.float64)
                if theta.shape != state.theta.shape or covariance.shape != state.covariance.shape or not np.isfinite(theta).all() or not np.isfinite(covariance).all():
                    raise ValueError("invalid two-output proposal state")
                next_state = _parameter_state(theta,covariance,state.vector_update_count+1)
            record = {"phase":phase,"updated":phase != "prefix","shared_transition_id":transition_id,
                "features_per_output":features.tolist(),"preupdate_prediction":{"next_q_rad":list(predicted_q),"next_v_rad_s":list(predicted_v)},
                "observed_next_v_rad_s":list(labels),"output_records":[{**p,"committed":True} for p in proposals],
                "vector_update_count":next_state.vector_update_count,"scalar_update_count":2*next_state.vector_update_count,
                "committed_scalar_updates":0 if phase == "prefix" else 2,
                "parameter_fingerprint_before":before,"parameter_fingerprint_after":_digest(self._parameter_record(next_state))}
            if phase != "prefix":
                # This is the only publish operation: interruption on either
                # side leaves all parameters and counters wholly old or new.
                self._state = next_state
            return record
        except BaseException as exc:
            actual_state = self._state
            committed = 2*(actual_state.vector_update_count-state.vector_update_count)
            ledger=PairUpdateError(exc,
                proposed_outputs=[{**p,"committed":committed == 2} for p in proposals],
                snapshot=self._snapshot_state(actual_state),committed_scalar_updates=committed)
            if isinstance(exc,(KeyboardInterrupt,SystemExit,OSError)):
                exc.pair_update_accounting=ledger.to_dict()
                raise
            raise ledger from exc


class DiagonalPairBodyModel(PairBodyModel):
    def __init__(self,qref,*,dt=.02,trainable=True):
        super().__init__(qref,structure="diagonal_hinge5",dt=dt,trainable=trainable)


class CoupledPairBodyModel(PairBodyModel):
    def __init__(self,qref,*,dt=.02,trainable=True):
        super().__init__(qref,structure="coupled_hinge9",dt=dt,trainable=trainable)


def update_shared_models(models: Mapping[str,PairBodyModel],q,v,u,next_v,*,transition_id,phase="identification"):
    """Same two scalar labels for every model; retain earlier successful commits."""
    if not models or any(not isinstance(model,PairBodyModel) for model in models.values()):
        raise ValueError("nonempty named pair models required")
    if len({id(model) for model in models.values()}) != len(models):
        raise ValueError("each shared transition must update distinct model objects exactly once")
    completed={}
    for name,model in models.items():
        try:
            completed[name]=model.update(q,v,u,next_v,phase=phase,transition_id=transition_id)
        except BaseException as exc:
            ledger=SharedPairUpdateError(exc,failed_model=name,completed_records=completed,
                snapshots={key:item.snapshot() for key,item in models.items()},transition_id=transition_id)
            if isinstance(exc,(KeyboardInterrupt,SystemExit,OSError)):
                exc.shared_pair_update_accounting=ledger.to_dict()
                raise
            raise ledger from exc
    return completed


@dataclass(frozen=True)
class PairCandidateRecord:
    torque: tuple[float,float]
    feasible: bool
    cost: float | None
    rejection_reason: str | None
    completed_prediction_steps: int
    pair_prediction_attempts: int
    scalar_prediction_attempts: int
    scalar_counts_complete: bool


@dataclass(frozen=True)
class PairMPCDecision:
    torque: tuple[float,float]
    feasible_candidates: int
    fallback: bool
    cost: float | None
    predicted_q: tuple[tuple[float,float],...]
    predicted_v: tuple[tuple[float,float],...]
    pair_prediction_attempts: int
    pair_prediction_successes: int
    scalar_prediction_attempts: int
    scalar_prediction_successes: int
    failed_pair_prediction_attempts: int
    scalar_counts_complete: bool
    scalar_counts_is_lower_bound: bool
    unknown_scalar_failure_count: int
    candidate_records: tuple[PairCandidateRecord,...]

    def to_dict(self):
        return asdict(self)


class FixedPairMPC:
    """H15 constant-vector search with identical original per-axis settings."""
    def __init__(self,model:PairBodyModel,joint_ranges,config:MPCConfig|None=None):
        if not isinstance(model,PairBodyModel):
            raise TypeError("model must be a PairBodyModel")
        self.model=model
        self.config=MPCConfig() if config is None else config
        if not isinstance(self.config,MPCConfig):
            raise TypeError("config must be MPCConfig")
        limits=np.asarray(joint_ranges,dtype=float)
        if limits.shape != (2,2) or not np.isfinite(limits).all() or np.any(limits[:,0]>=limits[:,1]):
            raise ValueError("two finite ordered public joint ranges required")
        self.joint_ranges=tuple(tuple(float(x) for x in row) for row in limits)
        cfg=self.config
        self.forecast_bounds=tuple((max(model.qref[i]-cfg.local_position_radius_rad,limits[i,0]-cfg.prediction_limit_tolerance_rad),
                                    min(model.qref[i]+cfg.local_position_radius_rad,limits[i,1]+cfg.prediction_limit_tolerance_rad)) for i in range(2))
        self.target_bounds=tuple((max(model.qref[i]-cfg.local_position_radius_rad,limits[i,0]+cfg.target_limit_margin_rad),
                                  min(model.qref[i]+cfg.local_position_radius_rad,limits[i,1]-cfg.target_limit_margin_rad)) for i in range(2))
        self._axis_candidates=tuple(float(x) for x in np.linspace(-cfg.torque_limit_nm,cfg.torque_limit_nm,cfg.candidate_count))
        self._candidates=tuple(product(self._axis_candidates,repeat=2))

    def spec(self):
        return {"config_per_axis":asdict(self.config),"qref_rad":list(self.model.qref),
                "joint_ranges_rad":[list(row) for row in self.joint_ranges],
                "forecast_bounds_rad":[list(row) for row in self.forecast_bounds],
                "target_bounds_rad":[list(row) for row in self.target_bounds],
                "axis_candidates_nm":list(self._axis_candidates),"vector_candidate_count":len(self._candidates),
                "vector_candidates_nm":[list(row) for row in self._candidates],
                "action_rollout":"same constant two-axis vector over the full horizon; apply first command",
                "target_information":"current two-axis target only; no transition preview or future target input",
                "cost":"original scalar cost per axis, summed across axes; change at first step only",
                "tie_break":"exact cost, sum(abs(u)), signed u0, signed u1","fallback_nm":[0.,0.],
                "prediction_count_units":"one pair attempt calls up to two scalar velocity heads; failures explicitly counted",
                "physical_queries":0}

    def parameter_fingerprint(self):
        return _digest(self.spec())

    def select(self,q,v,target_q,*,previous_torque=(0.,0.)):
        position,velocity,target,previous = (_pair(name,value) for name,value in (
            ("q",q),("v",v),("target_q",target_q),("previous_torque",previous_torque)))
        cfg=self.config
        if any(abs(u)>cfg.torque_limit_nm for u in previous):
            raise ValueError("previous vector torque exceeds per-axis fixed permission")
        if any(not self.target_bounds[i][0] <= target[i] <= self.target_bounds[i][1] for i in range(2)):
            raise ValueError("current target must be local and inside each public limit margin")
        feasible=[]
        records=[]
        pair_attempts=pair_successes=scalar_attempts=scalar_successes=unknown_failures=0
        for torque in self._candidates:
            predicted_q,predicted_v=position,velocity
            trajectory_q,trajectory_v=[],[]
            axis_costs=[cfg.change_weight*(torque[i]-previous[i])**2 for i in range(2)]
            reason=None
            candidate_pair=candidate_scalar=0
            candidate_counts_complete=True
            for _ in range(cfg.horizon):
                pair_attempts+=1
                candidate_pair+=1
                try:
                    predicted_q,predicted_v=self.model.predict(predicted_q,predicted_v,torque)
                except ValueError as exc:
                    if isinstance(exc,PairPredictionError):
                        scalar_attempts+=exc.scalar_prediction_attempts
                        candidate_scalar+=exc.scalar_prediction_attempts
                        scalar_successes+=exc.scalar_prediction_successes
                    else:
                        unknown_failures+=1
                        candidate_counts_complete=False
                    reason=f"prediction_error:{type(exc).__name__}"
                    break
                except BaseException as exc:
                    # Keep original exception semantics (especially IO and
                    # interrupts) and expose all prior mathematical cost.
                    head_cost=getattr(exc,"pair_prediction_accounting",None)
                    if head_cost is not None:
                        scalar_attempts+=head_cost["scalar_prediction_attempts"]
                        scalar_successes+=head_cost["scalar_prediction_successes"]
                    else:
                        unknown_failures+=1
                    exc.pair_planning_accounting={
                        "pair_prediction_attempts":pair_attempts,"pair_prediction_successes":pair_successes,
                        "scalar_prediction_attempts":scalar_attempts,"scalar_prediction_successes":scalar_successes,
                        "failed_pair_prediction_attempts":pair_attempts-pair_successes,
                        "scalar_counts_complete":unknown_failures == 0,
                        "scalar_counts_is_lower_bound":unknown_failures>0,
                        "unknown_scalar_failure_count":unknown_failures}
                    raise
                pair_successes+=1
                scalar_attempts+=2
                scalar_successes+=2
                candidate_scalar+=2
                if any(not self.forecast_bounds[i][0] <= predicted_q[i] <= self.forecast_bounds[i][1] for i in range(2)):
                    reason="forecast_position_bounds"
                    break
                if any(abs(predicted_v[i])>cfg.velocity_limit_rad_s for i in range(2)):
                    reason="forecast_velocity_bound"
                    break
                trajectory_q.append(tuple(predicted_q))
                trajectory_v.append(tuple(predicted_v))
                for i in range(2):
                    axis_costs[i]+=(cfg.position_weight*(predicted_q[i]-target[i])**2
                        +cfg.velocity_weight*predicted_v[i]**2+cfg.effort_weight*torque[i]**2)
                if not np.isfinite(axis_costs).all() or not np.isfinite(sum(axis_costs)):
                    reason="nonfinite_cost"
                    break
            else:
                cost=sum(axis_costs)
                feasible.append((cost,sum(abs(u) for u in torque),*torque,tuple(trajectory_q),tuple(trajectory_v)))
            ok=reason is None and len(trajectory_q) == cfg.horizon
            records.append(PairCandidateRecord(torque,ok,sum(axis_costs) if ok else None,reason,
                len(trajectory_q),candidate_pair,candidate_scalar,candidate_counts_complete))
        if feasible:
            cost,_,u0,u1,trajectory_q,trajectory_v=min(feasible)
            torque=(u0,u1)
        else:
            cost=None
            torque=(0.,0.)
            trajectory_q=trajectory_v=()
        return PairMPCDecision(torque,len(feasible),not feasible,cost,trajectory_q,trajectory_v,
            pair_attempts,pair_successes,scalar_attempts,scalar_successes,pair_attempts-pair_successes,
            unknown_failures == 0,unknown_failures>0,unknown_failures,tuple(records))
