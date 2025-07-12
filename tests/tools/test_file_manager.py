import pytest
import os
import shutil
from aos.tools.plugins.file_manager import FileManagerTool

# Fixture pytest pour créer un environnement de test propre
@pytest.fixture
def file_manager_setup():
    """Crée un workspace de test et le nettoie après le test."""
    workspace_dir = "./test_workspace"
    # S'assurer que le répertoire est vide avant de commencer
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir)
    
    # Création du FileManagerTool
    fm_tool = FileManagerTool(workspace_dir=workspace_dir)
    
    # yield retourne l'outil au test
    yield fm_tool
    
    # Ce code est exécuté après la fin du test (nettoyage)
    shutil.rmtree(workspace_dir)

# --- DEBUT DES TESTS ---

@pytest.mark.asyncio
async def test_get_safe_path_allows_access_within_workspace(file_manager_setup):
    """
    Vérifie que _get_safe_path résout correctement un chemin valide
    à l'intérieur du workspace.
    """
    fm_tool = file_manager_setup
    safe_path = fm_tool._get_safe_path("test_file.txt")
    
    expected_path = os.path.abspath(os.path.join(fm_tool.workspace_dir, "test_file.txt"))
    assert safe_path == expected_path

@pytest.mark.asyncio
async def test_get_safe_path_prevents_path_traversal(file_manager_setup):
    """
    Vérifie que _get_safe_path lève une PermissionError lors d'une
    tentative d'accès en dehors du workspace (Path Traversal).
    """
    fm_tool = file_manager_setup
    
    # Liste des tentatives de path traversal
    malicious_paths = [
        "../another_dir/file.txt",
        "../../../../etc/passwd",
        "/etc/passwd" # Chemin absolu
    ]
    
    for path in malicious_paths:
        with pytest.raises(PermissionError) as excinfo:
            fm_tool._get_safe_path(path)
        # Vérifie que le message d'erreur est bien celui attendu
        assert "Access denied" in str(excinfo.value)

@pytest.mark.asyncio
async def test_write_and_read_file_successfully(file_manager_setup):
    """
    Teste le cycle complet d'écriture puis de lecture d'un fichier.
    """
    fm_tool = file_manager_setup
    file_content = "Hello, AOS!"
    file_path = "subdir/my_document.txt"
    agent_id = "test-agent-123"

    # 1. Écrire le fichier
    write_result = await fm_tool.execute({
        "operation": "write",
        "path": file_path,
        "content": file_content
    }, agent_id)
    
    assert write_result["status"] == "success"

    # 2. Lire le fichier pour vérifier le contenu
    read_result = await fm_tool.execute({
        "operation": "read",
        "path": file_path
    }, agent_id)

    assert read_result["status"] == "success"
    assert read_result["content"] == file_content