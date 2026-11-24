"""Validated native H3 laboratory parameters shared by UI backend and batch CLI."""
import math

DEFAULTS = dict(seed=20260920, seconds=5, steps=8, sampler='euler', turbo=True,
                lora_strength=1.0, shift_video=12.0, shift_audio=3.0, denoise=1.0)


def settings(values):
    if not isinstance(values, dict) or set(values)-set(DEFAULTS):
        raise ValueError('未知测试参数')
    result={**DEFAULTS, **values}
    for key,low,high in [('seed',0,2**53-1),('seconds',1,15),('steps',1,50),
                         ('lora_strength',0,2),('shift_video',0.1,30),('shift_audio',0.1,10),('denoise',0.01,1)]:
        value=result[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'{key} 应在 {low}–{high} 之间')
        if key in ('seed','steps') and int(value)!=value:raise ValueError(key+' 必须为整数')
    if result['sampler'] not in ('euler','res_multistep'):raise ValueError('不支持的采样器')
    if not isinstance(result['turbo'],bool):raise ValueError('Turbo 开关无效')
    return result
