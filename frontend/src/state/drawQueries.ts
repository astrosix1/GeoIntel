import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createDrawing, deleteDrawing, fetchDrawing, fetchDrawings, updateDrawing } from '../api/client';
import { useEntitlements } from './queries';

// Saved drawings are server state, fetched only for a premium user who has the panel open, and refreshed after each change
// the user makes (never behind their back).
const KEY = ['drawings'];

export function useDrawingsQuery(enabled: boolean) {
  const { premium } = useEntitlements();
  return useQuery({
    queryKey: KEY,
    queryFn: fetchDrawings,
    enabled: premium && enabled,
    retry: false,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useSaveDrawingMutation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name, data }: { id: string | null; name: string; data: unknown }) =>
      id ? updateDrawing(id, { name, data }) : createDrawing(name, data),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRenameDrawingMutation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => updateDrawing(id, { name }),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteDrawingMutation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteDrawing(id),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

export { fetchDrawing };
