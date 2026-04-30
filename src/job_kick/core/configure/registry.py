from job_kick.core.configure.step import ConfigureStep
from job_kick.core.configure.steps.default_source import DefaultSourceStep
from job_kick.core.configure.steps.llm_provider import LLMProviderStep
from job_kick.core.configure.steps.profile import ProfileStep


def get_steps() -> list[ConfigureStep]:
    return [DefaultSourceStep(), LLMProviderStep(), ProfileStep()]
