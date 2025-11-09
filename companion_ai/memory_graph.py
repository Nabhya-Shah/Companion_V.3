"""
Knowledge Graph Memory System for Companion AI

Inspired by Cognee's GraphRAG approach, this implements:
- Entity extraction and relationship detection
- Graph-based memory with temporal tracking
- Hybrid retrieval (graph + vector + temporal)
- Multiple search modes (GRAPH_COMPLETION, RAG_COMPLETION, RELATIONSHIPS, TEMPORAL)

Uses NetworkX for graph operations and lightweight embeddings for semantic search.
"""
import logging
import json
import pickle
import os
from typing import Dict, List, Tuple, Set, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import networkx as nx

logger = logging.getLogger(__name__)

# Define paths
MODULE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
GRAPH_PATH = os.path.join(DATA_DIR, 'knowledge_graph.pkl')
EMBEDDINGS_PATH = os.path.join(DATA_DIR, 'memory_embeddings.pkl')

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)


@dataclass
class Entity:
    """Represents an entity in the knowledge graph"""
    name: str
    entity_type: str  # person, place, thing, concept, event, etc.
    attributes: Dict[str, str]
    first_mentioned: str  # ISO timestamp
    last_mentioned: str  # ISO timestamp
    mention_count: int = 1
    importance: float = 0.5  # 0.0-1.0
    
    def to_dict(self):
        return asdict(self)


@dataclass
class Relationship:
    """Represents a relationship between entities"""
    source: str  # entity name
    target: str  # entity name
    relation_type: str  # likes, works_at, related_to, causes, etc.
    context: str  # The conversation context where this was mentioned
    timestamp: str  # ISO timestamp
    strength: float = 0.5  # 0.0-1.0
    
    def to_dict(self):
        return asdict(self)


class KnowledgeGraph:
    """
    Hybrid Knowledge Graph + Vector Memory System
    
    Combines:
    - NetworkX graph for entity relationships
    - Simple embeddings for semantic search
    - Temporal tracking for time-based queries
    """
    
    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()
        self.embeddings: Dict[str, List[float]] = {}
        self._load_graph()
        logger.info(f"Knowledge Graph initialized: {self.graph.number_of_nodes()} entities, {self.graph.number_of_edges()} relationships")
    
    def _load_graph(self):
        """Load graph from disk if exists"""
        if os.path.exists(GRAPH_PATH):
            try:
                with open(GRAPH_PATH, 'rb') as f:
                    data = pickle.load(f)
                    self.graph = data.get('graph', nx.DiGraph())
                    self.embeddings = data.get('embeddings', {})
                logger.info(f"✅ Loaded knowledge graph from {GRAPH_PATH}")
            except Exception as e:
                logger.error(f"Failed to load graph: {e}")
                self.graph = nx.DiGraph()
                self.embeddings = {}
    
    def _save_graph(self):
        """Persist graph to disk"""
        try:
            data = {
                'graph': self.graph,
                'embeddings': self.embeddings,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            with open(GRAPH_PATH, 'wb') as f:
                pickle.dump(data, f)
            logger.info(f"💾 Saved knowledge graph to {GRAPH_PATH}")
        except Exception as e:
            logger.error(f"Failed to save graph: {e}")
    
    def add_entity(self, entity: Entity) -> bool:
        """Add or update entity in graph"""
        try:
            now = datetime.now(timezone.utc).isoformat()
            
            if self.graph.has_node(entity.name):
                # Update existing entity
                node_data = self.graph.nodes[entity.name]
                node_data['last_mentioned'] = now
                node_data['mention_count'] = node_data.get('mention_count', 0) + 1
                node_data['attributes'].update(entity.attributes)
                logger.info(f"🔄 Updated entity: {entity.name}")
            else:
                # Add new entity
                entity.first_mentioned = now
                entity.last_mentioned = now
                self.graph.add_node(entity.name, **entity.to_dict())
                logger.info(f"✨ New entity: {entity.name} ({entity.entity_type})")
            
            self._save_graph()
            return True
        except Exception as e:
            logger.error(f"Failed to add entity {entity.name}: {e}")
            return False
    
    def add_relationship(self, rel: Relationship) -> bool:
        """Add or strengthen relationship between entities"""
        try:
            now = datetime.now(timezone.utc).isoformat()
            
            # Ensure both entities exist (create if needed)
            if not self.graph.has_node(rel.source):
                self.add_entity(Entity(rel.source, "unknown", {}, now, now))
            if not self.graph.has_node(rel.target):
                self.add_entity(Entity(rel.target, "unknown", {}, now, now))
            
            if self.graph.has_edge(rel.source, rel.target):
                # Strengthen existing relationship
                edge_data = self.graph.edges[rel.source, rel.target]
                edge_data['strength'] = min(1.0, edge_data.get('strength', 0.5) + 0.1)
                edge_data['last_updated'] = now
                edge_data['contexts'].append(rel.context)
                logger.info(f"🔗 Strengthened: {rel.source} -{rel.relation_type}→ {rel.target}")
            else:
                # Add new relationship
                rel.timestamp = now
                rel_dict = rel.to_dict()
                rel_dict['contexts'] = [rel.context]
                rel_dict['last_updated'] = now
                self.graph.add_edge(rel.source, rel.target, **rel_dict)
                logger.info(f"✨ New relationship: {rel.source} -{rel.relation_type}→ {rel.target}")
            
            self._save_graph()
            return True
        except Exception as e:
            logger.error(f"Failed to add relationship: {e}")
            return False
    
    def get_entity(self, name: str) -> Optional[Dict]:
        """Get entity data by name"""
        if self.graph.has_node(name):
            return dict(self.graph.nodes[name])
        return None
    
    def get_entity_relationships(self, name: str) -> List[Dict]:
        """Get all relationships for an entity"""
        if not self.graph.has_node(name):
            return []
        
        relationships = []
        
        # Outgoing relationships
        for target in self.graph.successors(name):
            edge_data = dict(self.graph.edges[name, target])
            relationships.append({
                'type': 'outgoing',
                'source': name,
                'target': target,
                **edge_data
            })
        
        # Incoming relationships  
        for source in self.graph.predecessors(name):
            edge_data = dict(self.graph.edges[source, name])
            relationships.append({
                'type': 'incoming',
                'source': source,
                'target': name,
                **edge_data
            })
        
        return relationships
    
    def find_path(self, source: str, target: str, max_depth: int = 3) -> Optional[List[str]]:
        """Find shortest path between two entities"""
        try:
            if self.graph.has_node(source) and self.graph.has_node(target):
                path = nx.shortest_path(self.graph, source, target)
                if len(path) <= max_depth + 1:
                    return path
        except nx.NetworkXNoPath:
            pass
        return None
    
    def get_neighbors(self, name: str, depth: int = 1) -> Set[str]:
        """Get all entities within N hops of the given entity"""
        if not self.graph.has_node(name):
            return set()
        
        neighbors = {name}
        current_level = {name}
        
        for _ in range(depth):
            next_level = set()
            for node in current_level:
                # Add successors (outgoing edges)
                next_level.update(self.graph.successors(node))
                # Add predecessors (incoming edges)
                next_level.update(self.graph.predecessors(node))
            neighbors.update(next_level)
            current_level = next_level
        
        return neighbors - {name}  # Exclude the source entity
    
    def search_by_type(self, entity_type: str) -> List[Dict]:
        """Find all entities of a given type"""
        results = []
        for node, data in self.graph.nodes(data=True):
            if data.get('entity_type') == entity_type:
                results.append({'name': node, **data})
        return results
    
    def search_temporal(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
        """Find entities or relationships within a time range"""
        results = []
        
        for node, data in self.graph.nodes(data=True):
            last_mentioned = data.get('last_mentioned')
            if last_mentioned:
                if start_date and last_mentioned < start_date:
                    continue
                if end_date and last_mentioned > end_date:
                    continue
                results.append({'type': 'entity', 'name': node, **data})
        
        return results
    
    def get_most_important_entities(self, limit: int = 10) -> List[Dict]:
        """Get entities ranked by importance (mention count + connections)"""
        entity_scores = []
        
        for node, data in self.graph.nodes(data=True):
            # Score = mention_count + in_degree + out_degree + importance
            mention_score = data.get('mention_count', 1)
            degree_score = self.graph.in_degree(node) + self.graph.out_degree(node)
            importance = data.get('importance', 0.5)
            
            total_score = mention_score + degree_score + (importance * 10)
            entity_scores.append({
                'name': node,
                'score': total_score,
                **data
            })
        
        entity_scores.sort(key=lambda x: x['score'], reverse=True)
        return entity_scores[:limit]
    
    def search_keyword(self, query: str) -> List[Dict]:
        """Simple keyword-based search across entities and relationships"""
        query_lower = query.lower()
        results = []
        
        # Search entities
        for node, data in self.graph.nodes(data=True):
            if query_lower in node.lower():
                results.append({
                    'type': 'entity',
                    'name': node,
                    'match_type': 'name',
                    **data
                })
            else:
                # Check attributes
                for key, value in data.get('attributes', {}).items():
                    if query_lower in str(value).lower():
                        results.append({
                            'type': 'entity',
                            'name': node,
                            'match_type': f'attribute:{key}',
                            **data
                        })
                        break
        
        # Search relationships
        for source, target, data in self.graph.edges(data=True):
            relation = data.get('relation_type', '')
            context = data.get('context', '')
            
            if query_lower in relation.lower() or query_lower in context.lower():
                results.append({
                    'type': 'relationship',
                    'source': source,
                    'target': target,
                    'match_type': 'relationship',
                    **data
                })
        
        return results
    
    def get_stats(self) -> Dict:
        """Get graph statistics"""
        return {
            'total_entities': self.graph.number_of_nodes(),
            'total_relationships': self.graph.number_of_edges(),
            'entity_types': self._count_entity_types(),
            'avg_connections': self.graph.number_of_edges() / max(self.graph.number_of_nodes(), 1),
            'most_connected': self._get_most_connected(5)
        }
    
    def _count_entity_types(self) -> Dict[str, int]:
        """Count entities by type"""
        counts = {}
        for _, data in self.graph.nodes(data=True):
            entity_type = data.get('entity_type', 'unknown')
            counts[entity_type] = counts.get(entity_type, 0) + 1
        return counts
    
    def _get_most_connected(self, limit: int = 5) -> List[Dict]:
        """Get most connected entities"""
        connections = []
        for node in self.graph.nodes():
            degree = self.graph.in_degree(node) + self.graph.out_degree(node)
            if degree > 0:
                connections.append({
                    'name': node,
                    'connections': degree
                })
        connections.sort(key=lambda x: x['connections'], reverse=True)
        return connections[:limit]
    
    def export_graph_json(self) -> str:
        """Export graph as JSON for visualization"""
        nodes = []
        for node, data in self.graph.nodes(data=True):
            nodes.append({
                'id': node,
                'label': node,
                **data
            })
        
        edges = []
        for source, target, data in self.graph.edges(data=True):
            edges.append({
                'source': source,
                'target': target,
                **data
            })
        
        return json.dumps({
            'nodes': nodes,
            'edges': edges
        }, indent=2)


# Global instance
_knowledge_graph: Optional[KnowledgeGraph] = None


def get_knowledge_graph() -> KnowledgeGraph:
    """Get or create global knowledge graph instance"""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraph()
    return _knowledge_graph


def extract_entities_and_relationships(user_message: str, ai_response: str) -> Tuple[List[Entity], List[Relationship]]:
    """
    Extract entities and relationships from conversation
    
    This is a simplified version - in production you'd use:
    - NER (Named Entity Recognition) models
    - Relationship extraction models
    - LLM-based extraction with structured output
    
    For now, we'll use a lightweight approach with LLM extraction
    """
    from companion_ai.llm_interface import groq_memory_client
    
    if not groq_memory_client:
        logger.warning("Memory client not available for entity extraction")
        return [], []
    
    # Use LLM to extract structured data
    prompt = f"""Analyze this conversation and extract entities and relationships.

User: {user_message}
AI: {ai_response}

Return STRICT JSON:
{{
  "entities": [
    {{"name": "...", "type": "person|place|thing|concept|event", "attributes": {{"key": "value"}}}},
    ...
  ],
  "relationships": [
    {{"source": "entity1", "target": "entity2", "type": "likes|works_at|related_to|causes|...", "context": "brief context"}},
    ...
  ]
}}

Only extract MEANINGFUL entities and relationships. Skip common words. Focus on:
- People, places, organizations
- Important concepts, topics, events
- Clear relationships between entities
- User preferences, interests, facts

Return JSON only:"""

    try:
        response = groq_memory_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500
        )
        
        import re
        result_text = response.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        
        if match:
            data = json.loads(match.group())
            
            entities = []
            for e in data.get('entities', []):
                entities.append(Entity(
                    name=e['name'],
                    entity_type=e.get('type', 'unknown'),
                    attributes=e.get('attributes', {}),
                    first_mentioned="",  # Will be set by KnowledgeGraph
                    last_mentioned="",
                    importance=0.7  # Default importance
                ))
            
            relationships = []
            for r in data.get('relationships', []):
                relationships.append(Relationship(
                    source=r['source'],
                    target=r['target'],
                    relation_type=r.get('type', 'related_to'),
                    context=r.get('context', ''),
                    timestamp=""  # Will be set by KnowledgeGraph
                ))
            
            logger.info(f"📊 Extracted {len(entities)} entities, {len(relationships)} relationships")
            return entities, relationships
            
    except Exception as e:
        logger.error(f"Entity extraction failed: {e}")
    
    return [], []


def add_conversation_to_graph(user_message: str, ai_response: str):
    """Process conversation and add to knowledge graph"""
    try:
        kg = get_knowledge_graph()
        
        # Extract entities and relationships
        entities, relationships = extract_entities_and_relationships(user_message, ai_response)
        
        # Add to graph
        for entity in entities:
            kg.add_entity(entity)
        
        for rel in relationships:
            kg.add_relationship(rel)
        
        logger.info(f"✅ Added conversation to knowledge graph")
        
    except Exception as e:
        logger.error(f"Failed to add conversation to graph: {e}")


def search_graph(query: str, mode: str = "GRAPH_COMPLETION", limit: int = 10) -> List[Dict]:
    """
    Multi-modal graph search
    
    Modes:
    - GRAPH_COMPLETION: Find entity + neighbors + relationships
    - KEYWORD: Simple keyword search
    - RELATIONSHIPS: Find relationships involving query terms
    - TEMPORAL: Recent entities/relationships
    - IMPORTANT: Most important entities
    """
    kg = get_knowledge_graph()
    
    if mode == "GRAPH_COMPLETION":
        # Find entity and expand with neighbors
        results = kg.search_keyword(query)
        
        # For each entity found, add neighbors
        expanded = []
        for result in results[:3]:  # Limit expansion
            if result.get('type') == 'entity':
                name = result['name']
                expanded.append(result)
                
                # Add relationships
                relationships = kg.get_entity_relationships(name)
                expanded.extend(relationships[:5])
                
                # Add close neighbors
                neighbors = kg.get_neighbors(name, depth=1)
                for neighbor in list(neighbors)[:5]:
                    neighbor_data = kg.get_entity(neighbor)
                    if neighbor_data:
                        expanded.append({
                            'type': 'related_entity',
                            'name': neighbor,
                            **neighbor_data
                        })
        
        return expanded[:limit]
    
    elif mode == "KEYWORD":
        return kg.search_keyword(query)[:limit]
    
    elif mode == "RELATIONSHIPS":
        # Focus on relationships
        results = kg.search_keyword(query)
        return [r for r in results if r.get('type') == 'relationship'][:limit]
    
    elif mode == "TEMPORAL":
        # Recent entities
        return kg.search_temporal()[:limit]
    
    elif mode == "IMPORTANT":
        # Most important entities
        return kg.get_most_important_entities(limit)
    
    else:
        return kg.search_keyword(query)[:limit]


def get_graph_stats() -> Dict:
    """Get knowledge graph statistics"""
    kg = get_knowledge_graph()
    return kg.get_stats()


def export_graph() -> str:
    """Export knowledge graph as JSON"""
    kg = get_knowledge_graph()
    return kg.export_graph_json()


# Initialize on import
logger.info("📊 Knowledge Graph Memory System loaded")
