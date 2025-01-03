# Wingspan Implementation Guide

## Project Overview
This project implements the board game Wingspan with the goal of creating a platform for AI experimentation, particularly focusing on deep reinforcement learning and comparing different AI approaches.

## Current State
- Basic game structure implemented
- Core data classes defined (Bird, Player, GameState, etc.)
- Initial game rules documented
- Basic action structure defined

## Key Design Decisions

### Architecture Choice
Selected a hybrid approach combining:
- State-Action-State framework for clean game logic
- MCTS-compatible design for future AI implementation
- Controlled randomness for reproducible gameplay

Justification:
1. Enables efficient simulation of many games
2. Supports both traditional AI and deep learning approaches
3. Maintains clean separation between game logic and AI concerns
4. Allows for reproducible gameplay when needed

### Core Design Principles
1. **Explicit Randomness Control**
   - All random events (dice rolls, card draws) managed through controlled RNG
   - Enables reproducible gameplay for training

2. **Clear State Management**
   - Distinct game phases
   - Explicit handling of probabilistic events
   - Efficient state copying for simulations


3. **ML-Ready Architecture**
   - Clear action space definition
   - Observable game state
   - Step-based interface matching ML frameworks

## Next Steps

### 1. Core Game Logic Completion
- [ ] Implement controlled randomness system
- [ ] Complete action resolution system
- [ ] Add game phase management
- [ ] Implement state copying functionality
- [ ] Add validation for all game rules

### 2. State Management Enhancement
- [ ] Design efficient state representation
- [ ] Implement state serialization
- [ ] Add state validation utilities
- [ ] Create state observation interface

### 3. Action System Refinement
- [ ] Complete action validation system
- [ ] Implement action resolution pipeline
- [ ] Add action space utilities
- [ ] Create action indexing system for ML

### 4. Testing Infrastructure
- [ ] Create comprehensive test suite
- [ ] Add game state validators
- [ ] Implement game replay system
- [ ] Create performance benchmarks

### 5. Data Collection Framework
- [ ] Design game logging system
- [ ] Create data collection pipeline
- [ ] Implement replay storage
- [ ] Add analysis utilities

## Future Considerations

### ML Integration
- Will need to create numpy/tensor representations of game state
- Need to define clear observation space
- Consider performance optimizations for large-scale training

### AI Implementation
- Plan to support multiple AI approaches:
  - Deep Learning (AlphaZero-style)
  - MCTS
  - Traditional game AI techniques
- Need to benchmark different approaches

### Open Questions
1. Optimal state representation for ML
2. Performance requirements for large-scale training
3. Best approach for handling partial observability
4. Trade-offs between different AI approaches

## Implementation Guidelines

### Code Structure
```python
class GameState:
    def __init__(self):
        self.phase = GamePhase.PLAYER_DECISION
        self.rng = np.random.RandomState()  # For reproducibility
        
    def get_valid_actions(self) -> List[Action]:
        """Get all valid actions in current state"""
        pass

    def step(self, action: Action) -> Tuple[GameState, List[float], bool]:
        """
        Execute action and return (new_state, rewards, done)
        Handles both deterministic and chance outcomes
        """
        pass

    def get_observation(self) -> Dict:
        """Get complete game state observation"""
        pass

    def set_random_seed(self, seed: int):
        """Set RNG seed for reproducible behavior"""
        pass
```

### Key Interfaces
1. **Action Interface**
   - Clear definition of all possible actions
   - Conversion to/from ML-friendly format
   - Validation system

2. **State Interface**
   - Complete game state representation
   - Efficient copying mechanism
   - Observation generation

3. **Randomness Control**
   - Centralized RNG management
   - Reproducible gameplay option
   - Seed management

## Success Criteria
1. Clean, maintainable codebase
2. Efficient game simulation
3. Support for multiple AI approaches
4. Reproducible gameplay
5. Comprehensive test coverage
6. Clear documentation

## Development Priority
1. Complete core game mechanics
2. Implement state management
3. Add action system
4. Create testing infrastructure
5. Develop data collection system
6. Add ML interfaces

This guide should be updated as new decisions are made or requirements change.